import uuid
from decimal import Decimal

from sqlalchemy import or_, select

from oryn.connectors.base import ContactDTO, ContactIn, DealDTO, DealIn, DealPatch
from oryn.connectors.errors import NonRetryableConnectorError
from oryn.connectors.sandbox._common import SandboxBase
from oryn.models import SbContact, SbDeal


class SandboxCRM(SandboxBase):
    async def get_contact(self, contact_id: uuid.UUID) -> ContactDTO:
        await self.faults.maybe_fail("crm.get_contact")
        c = await self.s.get(SbContact, contact_id)
        if not c:
            raise NonRetryableConnectorError(f"contact {contact_id} not found", provider="sandbox", status_code=404)
        return ContactDTO.model_validate(c)

    async def find_contact(self, email: str | None = None, phone: str | None = None) -> ContactDTO | None:
        await self.faults.maybe_fail("crm.find_contact")
        conds = []
        if email:
            conds.append(SbContact.email == email.lower())
        if phone:
            conds.append(SbContact.phone == phone)
        if not conds:
            return None
        c = (await self.s.execute(select(SbContact).where(or_(*conds)).limit(1))).scalar_one_or_none()
        return ContactDTO.model_validate(c) if c else None

    async def upsert_contact(self, data: ContactIn) -> ContactDTO:
        await self.faults.maybe_fail("crm.upsert_contact")
        existing = await self.find_contact(data.email, data.phone)
        c = await self.s.get(SbContact, existing.id) if existing else None
        if c is None:
            c = SbContact(tenant_id=self.tenant_id, name=data.name, status="lead")
            self.s.add(c)
        c.name = data.name
        c.email = (data.email or c.email or "").lower() or None
        c.phone = data.phone or c.phone
        c.company = data.company or c.company
        c.source = data.source or c.source
        c.attributes = {**(c.attributes or {}), **data.attributes}
        await self.s.flush()
        await self.s.refresh(c)
        return ContactDTO.model_validate(c)

    async def create_deal(self, data: DealIn, idempotency_key: str) -> DealDTO:
        if (prior := await self._replay(idempotency_key)) is not None:
            return DealDTO.model_validate(prior)
        await self.faults.maybe_fail("crm.create_deal")
        d = SbDeal(tenant_id=self.tenant_id, contact_id=data.contact_id, title=data.title, amount_usd=data.amount_usd)
        self.s.add(d)
        await self.s.flush()
        await self.s.refresh(d)
        dto = DealDTO.model_validate(d)
        await self._record("crm.create_deal", idempotency_key, dto.model_dump(mode="json"))
        return dto

    async def _deal(self, deal_id: uuid.UUID) -> SbDeal:
        d = await self.s.get(SbDeal, deal_id)
        if not d:
            raise NonRetryableConnectorError(f"deal {deal_id} not found", provider="sandbox", status_code=404)
        return d

    async def update_deal(self, deal_id: uuid.UUID, patch: DealPatch, idempotency_key: str) -> DealDTO:
        if (prior := await self._replay(idempotency_key)) is not None:
            return DealDTO.model_validate(prior)
        await self.faults.maybe_fail("crm.update_deal")
        d = await self._deal(deal_id)
        if patch.stage is not None:
            d.stage = patch.stage
        if patch.amount_usd is not None:
            d.amount_usd = patch.amount_usd
        await self.s.flush()
        dto = DealDTO.model_validate(d)
        await self._record("crm.update_deal", idempotency_key, dto.model_dump(mode="json"))
        return dto

    async def apply_discount(self, deal_id: uuid.UUID, discount_pct: float, idempotency_key: str) -> DealDTO:
        if (prior := await self._replay(idempotency_key)) is not None:
            return DealDTO.model_validate(prior)
        if not 0 <= discount_pct <= 50:
            raise NonRetryableConnectorError("discount must be between 0 and 50%", provider="sandbox", status_code=422)
        await self.faults.maybe_fail("crm.apply_discount")
        d = await self._deal(deal_id)
        d.discount_pct = Decimal(str(discount_pct))
        await self.s.flush()
        dto = DealDTO.model_validate(d)
        await self._record("crm.apply_discount", idempotency_key, dto.model_dump(mode="json"))
        return dto

    async def add_note(self, contact_id: uuid.UUID, text: str) -> None:
        await self.faults.maybe_fail("crm.add_note")
        c = await self.s.get(SbContact, contact_id)
        if not c:
            raise NonRetryableConnectorError(f"contact {contact_id} not found", provider="sandbox", status_code=404)
        attrs = dict(c.attributes or {})
        attrs["notes"] = [*attrs.get("notes", []), text][-20:]
        c.attributes = attrs
        await self.s.flush()

    async def list_deals(self, contact_id: uuid.UUID | None = None) -> list[DealDTO]:
        await self.faults.maybe_fail("crm.list_deals")
        q = select(SbDeal).order_by(SbDeal.created_at)
        if contact_id:
            q = q.where(SbDeal.contact_id == contact_id)
        return [DealDTO.model_validate(d) for d in (await self.s.execute(q)).scalars()]
