"""Connector interfaces. Every provider (sandbox or real) implements these Protocols."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict


class _DTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ContactIn(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    source: str | None = None
    attributes: dict[str, Any] = {}


class ContactDTO(_DTO):
    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    company: str | None
    status: str
    attributes: dict[str, Any]


class DealIn(BaseModel):
    contact_id: uuid.UUID
    title: str
    amount_usd: Decimal


class DealPatch(BaseModel):
    stage: str | None = None
    amount_usd: Decimal | None = None


class DealDTO(_DTO):
    id: uuid.UUID
    contact_id: uuid.UUID
    title: str
    amount_usd: Decimal
    stage: str
    discount_pct: Decimal


class Slot(BaseModel):
    starts_at: datetime
    ends_at: datetime


class BookingDTO(_DTO):
    id: uuid.UUID
    title: str
    contact_id: uuid.UUID | None
    starts_at: datetime
    ends_at: datetime
    status: str


class InvoiceDTO(_DTO):
    id: uuid.UUID
    contact_id: uuid.UUID
    number: str
    amount_usd: Decimal
    status: str
    due_date: date
    refunded_usd: Decimal


class MessageDTO(_DTO):
    id: uuid.UUID
    channel: str
    direction: str
    to_addr: str | None
    subject: str | None
    body: str
    conversation_id: uuid.UUID | None


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]


class DocHit(BaseModel):
    id: uuid.UUID
    title: str
    snippet: str
    score: float


Preference = Literal["morning", "afternoon", "any"]


class CRM(Protocol):
    async def get_contact(self, contact_id: uuid.UUID) -> ContactDTO: ...
    async def find_contact(self, email: str | None = None, phone: str | None = None) -> ContactDTO | None: ...
    async def upsert_contact(self, data: ContactIn) -> ContactDTO: ...
    async def create_deal(self, data: DealIn, idempotency_key: str) -> DealDTO: ...
    async def update_deal(self, deal_id: uuid.UUID, patch: DealPatch, idempotency_key: str) -> DealDTO: ...
    async def apply_discount(self, deal_id: uuid.UUID, discount_pct: float, idempotency_key: str) -> DealDTO: ...
    async def add_note(self, contact_id: uuid.UUID, text: str) -> None: ...
    async def list_deals(self, contact_id: uuid.UUID | None = None) -> list[DealDTO]: ...


class Calendar(Protocol):
    async def find_slots(self, duration_min: int, within_days: int, prefer: Preference) -> list[Slot]: ...
    async def book(self, slot: Slot, title: str, contact_id: uuid.UUID | None, idempotency_key: str) -> BookingDTO: ...
    async def cancel(self, booking_id: uuid.UUID, idempotency_key: str) -> None: ...


class Billing(Protocol):
    async def create_invoice(self, contact_id: uuid.UUID, amount_usd: float, idempotency_key: str) -> InvoiceDTO: ...
    async def list_overdue(self) -> list[InvoiceDTO]: ...
    async def mark_paid(self, invoice_id: uuid.UUID, idempotency_key: str) -> InvoiceDTO: ...
    async def issue_refund(self, invoice_id: uuid.UUID, amount_usd: float, idempotency_key: str) -> InvoiceDTO: ...


class Messaging(Protocol):
    async def send_email(
        self, to: str, subject: str, body: str, idempotency_key: str, conversation_id: uuid.UUID | None = None
    ) -> MessageDTO: ...
    async def send_sms(
        self, to: str, body: str, idempotency_key: str, conversation_id: uuid.UUID | None = None
    ) -> MessageDTO: ...
    async def send_chat(self, conversation_id: uuid.UUID, body: str, idempotency_key: str) -> MessageDTO: ...


class Database(Protocol):
    async def query(self, sql: str, params: dict[str, Any], limit: int = 200) -> QueryResult: ...


class Docs(Protocol):
    async def search(self, query: str, k: int = 3) -> list[DocHit]: ...
