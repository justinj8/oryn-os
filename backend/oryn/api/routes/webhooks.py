from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from temporalio.client import Client

from oryn.api.deps import TenantContext, tenant_ctx
from oryn.core.db import system_session
from oryn.models import Tenant
from oryn.orchestration.client import temporal_client
from oryn.services.ingest import ingest_event

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


class IngestOut(BaseModel):
    event_id: str
    created: bool
    run_ids: list[str]


async def tenant_by_slug(slug: str) -> Tenant:
    async with system_session() as s:
        t = (await s.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one_or_none()
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown tenant")
    return t


@router.post("/{tenant_slug}/events/{event_type}", status_code=202, response_model=IngestOut)
async def generic_event(
    tenant_slug: str,
    event_type: str,
    payload: dict[str, Any] = Body(...),
    idempotency_key: str | None = Header(default=None),
    ctx: TenantContext = Depends(tenant_ctx),
    client: Client = Depends(temporal_client),
) -> IngestOut:
    """Generic inbound event from any internal system (CRM webhook, form, cron, …)."""
    if not idempotency_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key header is required")
    tenant = await tenant_by_slug(tenant_slug)
    if tenant.id != ctx.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "credentials do not belong to this tenant")
    r = await ingest_event(client, tenant.id, event_type, "api", payload, idempotency_key)
    return IngestOut(event_id=str(r.event_id), created=r.created, run_ids=[str(x) for x in r.run_ids])
