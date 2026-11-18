"""Business tools agents can call. Risk levels drive the approval policy."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from oryn.connectors.base import ContactIn, DealIn, Slot
from oryn.models import ConnectorKind
from oryn.tools.registry import RiskLevel, ToolContext, ToolRegistry, ToolSpec


def _dump(m: Any) -> Any:
    if isinstance(m, BaseModel):
        return m.model_dump(mode="json")
    if isinstance(m, list):
        return [_dump(x) for x in m]
    return m


# ---------- input models
class FindContactIn(BaseModel):
    email: str | None = None
    phone: str | None = None


class ContactIdIn(BaseModel):
    contact_id: uuid.UUID


class ListDealsIn(BaseModel):
    contact_id: uuid.UUID | None = None


class FindSlotsIn(BaseModel):
    duration_min: int = Field(30, ge=15, le=240)
    within_days: int = Field(5, ge=1, le=30)
    prefer: Literal["morning", "afternoon", "any"] = "any"


class EmptyIn(BaseModel):
    pass


class QueryIn(BaseModel):
    sql: str
    params: dict[str, Any] = {}


class DocsSearchIn(BaseModel):
    query: str
    k: int = Field(3, ge=1, le=10)


class AddNoteIn(BaseModel):
    contact_id: uuid.UUID
    text: str


class CreateDealIn(BaseModel):
    contact_id: uuid.UUID
    title: str
    amount_usd: Decimal = Field(ge=0)


class BookIn(BaseModel):
    starts_at: datetime
    ends_at: datetime
    title: str
    contact_id: uuid.UUID | None = None


class CancelIn(BaseModel):
    booking_id: uuid.UUID


class SendEmailIn(BaseModel):
    to: str
    subject: str
    body: str
    conversation_id: uuid.UUID | None = None


class SendSmsIn(BaseModel):
    to: str
    body: str
    conversation_id: uuid.UUID | None = None


class CreateInvoiceIn(BaseModel):
    contact_id: uuid.UUID
    amount_usd: float = Field(gt=0)


class ApplyDiscountIn(BaseModel):
    deal_id: uuid.UUID
    discount_pct: float = Field(ge=0, le=100)


class RefundIn(BaseModel):
    invoice_id: uuid.UUID
    amount_usd: float = Field(gt=0)


class InvoiceIdIn(BaseModel):
    invoice_id: uuid.UUID


# ---------- handlers
async def find_contact(ctx: ToolContext, a: FindContactIn) -> dict:
    c = await ctx.connectors.crm.find_contact(a.email, a.phone)
    return {"found": c is not None, "contact": _dump(c)}


async def get_contact(ctx: ToolContext, a: ContactIdIn) -> dict:
    return {"contact": _dump(await ctx.connectors.crm.get_contact(a.contact_id))}


async def list_deals(ctx: ToolContext, a: ListDealsIn) -> dict:
    return {"deals": _dump(await ctx.connectors.crm.list_deals(a.contact_id))}


async def find_slots(ctx: ToolContext, a: FindSlotsIn) -> dict:
    return {"slots": _dump(await ctx.connectors.calendar.find_slots(a.duration_min, a.within_days, a.prefer))}


async def list_overdue(ctx: ToolContext, a: EmptyIn) -> dict:
    return {"invoices": _dump(await ctx.connectors.billing.list_overdue())}


async def db_query(ctx: ToolContext, a: QueryIn) -> dict:
    return _dump(await ctx.connectors.database.query(a.sql, a.params))


async def docs_search(ctx: ToolContext, a: DocsSearchIn) -> dict:
    return {"hits": _dump(await ctx.connectors.docs.search(a.query, a.k))}


async def upsert_contact(ctx: ToolContext, a: ContactIn) -> dict:
    return {"contact": _dump(await ctx.connectors.crm.upsert_contact(a))}


async def add_note(ctx: ToolContext, a: AddNoteIn) -> dict:
    await ctx.connectors.crm.add_note(a.contact_id, a.text)
    return {"ok": True}


async def create_deal(ctx: ToolContext, a: CreateDealIn) -> dict:
    d = await ctx.connectors.crm.create_deal(
        DealIn(contact_id=a.contact_id, title=a.title, amount_usd=a.amount_usd), ctx.idempotency_key
    )
    return {"deal": _dump(d)}


async def apply_discount(ctx: ToolContext, a: ApplyDiscountIn) -> dict:
    return {"deal": _dump(await ctx.connectors.crm.apply_discount(a.deal_id, a.discount_pct, ctx.idempotency_key))}


async def book(ctx: ToolContext, a: BookIn) -> dict:
    b = await ctx.connectors.calendar.book(
        Slot(starts_at=a.starts_at, ends_at=a.ends_at), a.title, a.contact_id, ctx.idempotency_key
    )
    return _dump(b)


async def cancel(ctx: ToolContext, a: CancelIn) -> dict:
    await ctx.connectors.calendar.cancel(a.booking_id, ctx.idempotency_key)
    return {"ok": True}


async def send_email(ctx: ToolContext, a: SendEmailIn) -> dict:
    m = await ctx.connectors.messaging.send_email(a.to, a.subject, a.body, ctx.idempotency_key, a.conversation_id)
    return {"message": _dump(m)}


async def send_sms(ctx: ToolContext, a: SendSmsIn) -> dict:
    m = await ctx.connectors.messaging.send_sms(a.to, a.body, ctx.idempotency_key, a.conversation_id)
    return {"message": _dump(m)}


async def create_invoice(ctx: ToolContext, a: CreateInvoiceIn) -> dict:
    return {
        "invoice": _dump(await ctx.connectors.billing.create_invoice(a.contact_id, a.amount_usd, ctx.idempotency_key))
    }


async def issue_refund(ctx: ToolContext, a: RefundIn) -> dict:
    return {
        "invoice": _dump(await ctx.connectors.billing.issue_refund(a.invoice_id, a.amount_usd, ctx.idempotency_key))
    }


def register_catalog(reg: ToolRegistry) -> None:
    K, R = ConnectorKind, RiskLevel

    def add(name, desc, model, handler, risk, side_effect, kind, **kw):
        reg.register(ToolSpec(name, desc, model, risk, side_effect, kind, **kw), handler)

    # Read-only
    add("crm.find_contact", "Look up a contact by email or phone.", FindContactIn, find_contact, R.low, False, K.crm)
    add("crm.get_contact", "Fetch a contact by id.", ContactIdIn, get_contact, R.low, False, K.crm)
    add("crm.list_deals", "List deals, optionally for one contact.", ListDealsIn, list_deals, R.low, False, K.crm)
    add(
        "calendar.find_slots",
        "Find open appointment slots in business hours.",
        FindSlotsIn,
        find_slots,
        R.low,
        False,
        K.calendar,
    )
    add("billing.list_overdue", "List overdue open invoices.", EmptyIn, list_overdue, R.low, False, K.billing)
    add(
        "db.query",
        "Run a read-only SQL query against the internal data warehouse.",
        QueryIn,
        db_query,
        R.low,
        False,
        K.database,
    )
    add("docs.search", "Search the knowledge base (policies, FAQs).", DocsSearchIn, docs_search, R.low, False, K.docs)
    # Side effects
    add("crm.upsert_contact", "Create or update a contact.", ContactIn, upsert_contact, R.medium, True, K.crm)
    add("crm.add_note", "Add a note to a contact.", AddNoteIn, add_note, R.medium, True, K.crm)
    add("crm.create_deal", "Create a sales deal for a contact.", CreateDealIn, create_deal, R.medium, True, K.crm)
    add("calendar.book", "Book an appointment in an open slot.", BookIn, book, R.medium, True, K.calendar)
    add("calendar.cancel", "Cancel a booked appointment.", CancelIn, cancel, R.medium, True, K.calendar)
    add("messaging.send_email", "Send an email.", SendEmailIn, send_email, R.medium, True, K.email)
    add("messaging.send_sms", "Send an SMS.", SendSmsIn, send_sms, R.medium, True, K.sms)
    add("billing.create_invoice", "Create an invoice.", CreateInvoiceIn, create_invoice, R.medium, True, K.billing)
    # High risk: money moves
    add(
        "crm.apply_discount",
        "Apply a percentage discount to a deal.",
        ApplyDiscountIn,
        apply_discount,
        R.high,
        True,
        K.crm,
        percent_field="discount_pct",
    )
    add(
        "billing.issue_refund",
        "Refund part or all of an invoice.",
        RefundIn,
        issue_refund,
        R.high,
        True,
        K.billing,
        amount_field="amount_usd",
    )
