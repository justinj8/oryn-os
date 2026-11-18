import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from oryn.connectors.base import InvoiceDTO
from oryn.connectors.errors import NonRetryableConnectorError
from oryn.connectors.faults import FaultInjector
from oryn.connectors.sandbox._common import SandboxBase
from oryn.models import SbInvoice


class SandboxBilling(SandboxBase):
    def __init__(self, session, tenant_id: uuid.UUID, faults: FaultInjector, today: Callable[[], date] | None = None):
        super().__init__(session, tenant_id, faults)
        self.today = today or (lambda: datetime.now(UTC).date())

    async def _invoice(self, invoice_id: uuid.UUID) -> SbInvoice:
        inv = await self.s.get(SbInvoice, invoice_id)
        if not inv:
            raise NonRetryableConnectorError("invoice not found", provider="sandbox", status_code=404)
        return inv

    async def create_invoice(self, contact_id: uuid.UUID, amount_usd: float, idempotency_key: str) -> InvoiceDTO:
        if (prior := await self._replay(idempotency_key)) is not None:
            return InvoiceDTO.model_validate(prior)
        await self.faults.maybe_fail("billing.create_invoice")
        n = (await self.s.execute(select(func.count()).select_from(SbInvoice))).scalar_one()
        inv = SbInvoice(
            tenant_id=self.tenant_id,
            contact_id=contact_id,
            number=f"INV-{1001 + n}",
            amount_usd=Decimal(str(amount_usd)),
            status="open",
            due_date=self.today() + timedelta(days=14),
        )
        self.s.add(inv)
        await self.s.flush()
        await self.s.refresh(inv)
        dto = InvoiceDTO.model_validate(inv)
        await self._record("billing.create_invoice", idempotency_key, dto.model_dump(mode="json"))
        return dto

    async def list_overdue(self) -> list[InvoiceDTO]:
        await self.faults.maybe_fail("billing.list_overdue")
        rows = await self.s.execute(
            select(SbInvoice)
            .where(SbInvoice.status == "open", SbInvoice.due_date < self.today())
            .order_by(SbInvoice.due_date)
        )
        return [InvoiceDTO.model_validate(i) for i in rows.scalars()]

    async def mark_paid(self, invoice_id: uuid.UUID, idempotency_key: str) -> InvoiceDTO:
        if (prior := await self._replay(idempotency_key)) is not None:
            return InvoiceDTO.model_validate(prior)
        inv = await self._invoice(invoice_id)
        inv.status = "paid"
        await self.s.flush()
        dto = InvoiceDTO.model_validate(inv)
        await self._record("billing.mark_paid", idempotency_key, dto.model_dump(mode="json"))
        return dto

    async def issue_refund(self, invoice_id: uuid.UUID, amount_usd: float, idempotency_key: str) -> InvoiceDTO:
        if (prior := await self._replay(idempotency_key)) is not None:
            return InvoiceDTO.model_validate(prior)
        await self.faults.maybe_fail("billing.issue_refund")
        inv = await self._invoice(invoice_id)
        amount = Decimal(str(amount_usd))
        if amount <= 0 or inv.refunded_usd + amount > inv.amount_usd:
            raise NonRetryableConnectorError(
                f"refund of ${amount} exceeds refundable balance ${inv.amount_usd - inv.refunded_usd}",
                provider="sandbox",
                status_code=422,
            )
        inv.refunded_usd += amount
        if inv.refunded_usd == inv.amount_usd:
            inv.status = "refunded"
        await self.s.flush()
        dto = InvoiceDTO.model_validate(inv)
        await self._record("billing.issue_refund", idempotency_key, dto.model_dump(mode="json"))
        return dto
