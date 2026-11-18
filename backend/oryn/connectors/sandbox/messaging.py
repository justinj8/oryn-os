import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from oryn.connectors.base import MessageDTO
from oryn.connectors.faults import FaultInjector
from oryn.connectors.sandbox._common import SandboxBase
from oryn.models import SbMessage


class SandboxMessaging(SandboxBase):
    """Writes outbound messages to the sandbox outbox (visible in the dashboard)."""

    def __init__(self, session, tenant_id: uuid.UUID, faults: FaultInjector, now: Callable[[], datetime] | None = None):
        super().__init__(session, tenant_id, faults)
        self.now = now or (lambda: datetime.now(UTC))
        self.from_email = "agents@oryn.local"
        self.from_phone = "+15550000000"

    async def _send(
        self, channel: str, to: str | None, subject: str | None, body: str, key: str, conversation_id: uuid.UUID | None
    ) -> MessageDTO:
        if (prior := await self._replay(key)) is not None:
            return MessageDTO.model_validate(prior)
        await self.faults.maybe_fail(f"messaging.send_{channel}")
        msg = SbMessage(
            tenant_id=self.tenant_id,
            channel=channel,
            direction="out",
            to_addr=to,
            from_addr=self.from_email if channel == "email" else self.from_phone,
            subject=subject,
            body=body,
            conversation_id=conversation_id,
            sent_at=self.now(),
        )
        self.s.add(msg)
        await self.s.flush()
        dto = MessageDTO.model_validate(msg)
        await self._record(f"messaging.send_{channel}", key, dto.model_dump(mode="json"))
        return dto

    async def send_email(
        self, to: str, subject: str, body: str, idempotency_key: str, conversation_id: uuid.UUID | None = None
    ) -> MessageDTO:
        return await self._send("email", to, subject, body, idempotency_key, conversation_id)

    async def send_sms(
        self, to: str, body: str, idempotency_key: str, conversation_id: uuid.UUID | None = None
    ) -> MessageDTO:
        return await self._send("sms", to, None, body, idempotency_key, conversation_id)

    async def send_chat(self, conversation_id: uuid.UUID, body: str, idempotency_key: str) -> MessageDTO:
        return await self._send("chat", None, None, body, idempotency_key, conversation_id)
