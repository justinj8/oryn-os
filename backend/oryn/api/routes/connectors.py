import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from oryn.api.deps import TenantContext, require_role
from oryn.core.audit import record_audit
from oryn.core.config import get_settings
from oryn.core.db import tenant_session
from oryn.core.tenancy import Role
from oryn.models import (
    Connector,
    ConnectorKind,
    SbCalendarEvent,
    SbContact,
    SbDeal,
    SbDocument,
    SbInvoice,
    SbMessage,
    SbTicket,
)

router = APIRouter(prefix="/api", tags=["connectors"])


class FaultSettings(BaseModel):
    failure_rate: float = Field(0, ge=0, le=1)
    latency_ms: int = Field(0, ge=0, le=5000)
    fail_attempts: int = Field(0, ge=0, le=5)


class ConnectorOut(BaseModel):
    id: uuid.UUID
    kind: ConnectorKind
    provider: str
    name: str
    status: str
    settings: dict[str, Any]
    has_secrets: bool


class ConnectorPatch(BaseModel):
    settings: FaultSettings


def _effective_provider(c: Connector) -> str:
    s = get_settings()
    if c.kind == ConnectorKind.sms and s.twilio_account_sid:
        return "twilio"
    if c.kind == ConnectorKind.email and s.smtp_url:
        return "smtp"
    return c.provider


def _out(c: Connector) -> ConnectorOut:
    return ConnectorOut(
        id=c.id,
        kind=c.kind,
        provider=_effective_provider(c),
        name=c.name,
        status=c.status,
        settings=c.settings or {},
        has_secrets=c.config_encrypted is not None,
    )


@router.get("/connectors", response_model=list[ConnectorOut])
async def list_connectors(ctx: TenantContext = Depends(require_role(Role.viewer))) -> list[ConnectorOut]:
    async with tenant_session(ctx.tenant_id) as s:
        return [_out(c) for c in (await s.execute(select(Connector).order_by(Connector.kind))).scalars()]


@router.patch("/connectors/{connector_id}", response_model=ConnectorOut)
async def patch_connector(
    connector_id: uuid.UUID, body: ConnectorPatch, ctx: TenantContext = Depends(require_role(Role.admin))
) -> ConnectorOut:
    async with tenant_session(ctx.tenant_id) as s:
        c = await s.get(Connector, connector_id)
        if c is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "connector not found")
        before = dict(c.settings or {})
        c.settings = {**before, **body.settings.model_dump()}
        await record_audit(s, ctx, "connector.updated", "connector", c.id, before, c.settings)
        return _out(c)


SANDBOX = {
    "contacts": (SbContact, ["name", "email", "phone", "company", "status", "source", "attributes"]),
    "deals": (SbDeal, ["contact_id", "title", "amount_usd", "stage", "discount_pct"]),
    "calendar": (SbCalendarEvent, ["title", "contact_id", "starts_at", "ends_at", "status"]),
    "messages": (
        SbMessage,
        ["channel", "direction", "to_addr", "from_addr", "subject", "body", "conversation_id", "sent_at"],
    ),
    "invoices": (SbInvoice, ["contact_id", "number", "amount_usd", "status", "due_date", "refunded_usd"]),
    "tickets": (SbTicket, ["contact_id", "subject", "body", "status", "priority"]),
    "documents": (SbDocument, ["title", "body"]),
}


class SandboxPage(BaseModel):
    items: list[dict[str, Any]]
    total: int


@router.get("/sandbox/{resource}", response_model=SandboxPage)
async def browse_sandbox(
    resource: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: TenantContext = Depends(require_role(Role.viewer)),
) -> SandboxPage:
    if resource not in SANDBOX:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown sandbox resource '{resource}'")
    model, fields = SANDBOX[resource]
    async with tenant_session(ctx.tenant_id) as s:
        total = (await s.execute(select(func.count()).select_from(model))).scalar_one()
        rows = (await s.execute(select(model).order_by(model.created_at.desc()).limit(limit).offset(offset))).scalars()
        items = [{"id": r.id, "created_at": r.created_at, **{f: getattr(r, f) for f in fields}} for r in rows]
    return SandboxPage(items=items, total=total)
