import uuid
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from oryn.connectors.base import BookingDTO, Preference, Slot
from oryn.connectors.errors import NonRetryableConnectorError
from oryn.connectors.faults import FaultInjector
from oryn.connectors.sandbox._common import SandboxBase
from oryn.models import SbCalendarEvent

OPEN_HOUR, CLOSE_HOUR, MAX_SLOTS = 9, 17, 6


class SandboxCalendar(SandboxBase):
    def __init__(
        self,
        session,
        tenant_id: uuid.UUID,
        faults: FaultInjector,
        tz: str = "America/New_York",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(session, tenant_id, faults)
        self.tz = ZoneInfo(tz)
        self.now = now or (lambda: datetime.now(UTC))

    async def find_slots(self, duration_min: int, within_days: int, prefer: Preference) -> list[Slot]:
        await self.faults.maybe_fail("calendar.find_slots")
        now = self.now()
        horizon = now + timedelta(days=within_days + 3)  # +3 so weekends don't eat the window
        busy = (
            await self.s.execute(
                select(SbCalendarEvent.starts_at, SbCalendarEvent.ends_at).where(
                    SbCalendarEvent.status == "confirmed",
                    SbCalendarEvent.ends_at > now,
                    SbCalendarEvent.starts_at < horizon,
                )
            )
        ).all()
        step, dur = timedelta(minutes=30), timedelta(minutes=duration_min)
        candidates: list[Slot] = []
        day = now.astimezone(self.tz).date()
        business_days = 0
        while business_days < within_days:
            if day.weekday() < 5:
                business_days += 1
                t = datetime.combine(day, time(OPEN_HOUR), self.tz)
                close = datetime.combine(day, time(CLOSE_HOUR), self.tz)
                while t + dur <= close:
                    start, end = t.astimezone(UTC), (t + dur).astimezone(UTC)
                    if start > now and not any(b0 < end and start < b1 for b0, b1 in busy):
                        candidates.append(Slot(starts_at=start, ends_at=end))
                    t += step
            day += timedelta(days=1)
        if prefer != "any":

            def is_pref(s: Slot) -> bool:
                hour = s.starts_at.astimezone(self.tz).hour
                return hour < 12 if prefer == "morning" else hour >= 12

            candidates.sort(key=lambda s: (not is_pref(s), s.starts_at))
        return candidates[:MAX_SLOTS]

    async def book(self, slot: Slot, title: str, contact_id: uuid.UUID | None, idempotency_key: str) -> BookingDTO:
        if (prior := await self._replay(idempotency_key)) is not None:
            return BookingDTO.model_validate(prior)
        await self.faults.maybe_fail("calendar.book")
        clash = (
            await self.s.execute(
                select(SbCalendarEvent.id).where(
                    SbCalendarEvent.status == "confirmed",
                    SbCalendarEvent.starts_at < slot.ends_at,
                    SbCalendarEvent.ends_at > slot.starts_at,
                )
            )
        ).first()
        if clash:
            raise NonRetryableConnectorError("slot no longer available", provider="sandbox", status_code=409)
        ev = SbCalendarEvent(
            tenant_id=self.tenant_id,
            title=title,
            contact_id=contact_id,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
            status="confirmed",
        )
        self.s.add(ev)
        await self.s.flush()
        dto = BookingDTO.model_validate(ev)
        await self._record("calendar.book", idempotency_key, dto.model_dump(mode="json"))
        return dto

    async def cancel(self, booking_id: uuid.UUID, idempotency_key: str) -> None:
        if await self._replay(idempotency_key) is not None:
            return
        await self.faults.maybe_fail("calendar.cancel")
        ev = await self.s.get(SbCalendarEvent, booking_id)
        if not ev:
            raise NonRetryableConnectorError("booking not found", provider="sandbox", status_code=404)
        ev.status = "cancelled"
        await self._record("calendar.cancel", idempotency_key, {"id": str(booking_id)})
