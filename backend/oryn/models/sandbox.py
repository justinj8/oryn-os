"""The simulated outside world: a per-tenant CRM, calendar, inbox, billing system and docs."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from oryn.models.base import Base, TenantScoped


class SbContact(Base, TenantScoped):
    __tablename__ = "sb_contacts"
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    company: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="lead")
    source: Mapped[str | None] = mapped_column(String(32))
    attributes: Mapped[dict[str, Any]] = mapped_column(default=dict)


class SbDeal(Base, TenantScoped):
    __tablename__ = "sb_deals"
    contact_id: Mapped[uuid.UUID] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(300))
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    stage: Mapped[str] = mapped_column(String(32), default="qualified")
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(0))


class SbCalendarEvent(Base, TenantScoped):
    __tablename__ = "sb_calendar_events"
    title: Mapped[str] = mapped_column(String(300))
    contact_id: Mapped[uuid.UUID | None]
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="confirmed")


class SbMessage(Base, TenantScoped):
    __tablename__ = "sb_messages"
    channel: Mapped[str] = mapped_column(String(16), index=True)
    direction: Mapped[str] = mapped_column(String(8))
    to_addr: Mapped[str | None] = mapped_column(String(320))
    from_addr: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SbInvoice(Base, TenantScoped):
    __tablename__ = "sb_invoices"
    contact_id: Mapped[uuid.UUID] = mapped_column(index=True)
    number: Mapped[str] = mapped_column(String(32))
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(16), default="open")
    due_date: Mapped[date] = mapped_column(Date)
    refunded_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal(0))


class SbTicket(Base, TenantScoped):
    __tablename__ = "sb_tickets"
    contact_id: Mapped[uuid.UUID | None]
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    priority: Mapped[str] = mapped_column(String(16), default="normal")


class SbDocument(Base, TenantScoped):
    __tablename__ = "sb_documents"
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)


class SbActionLog(Base, TenantScoped):
    """Idempotency ledger for side-effecting sandbox calls."""

    __tablename__ = "sb_action_log"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    tool: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
