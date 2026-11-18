"""Simulator controls for the demo: fire a realistic event, or switch live traffic on."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from temporalio.client import Client

from oryn.api.deps import TenantContext, require_role
from oryn.api.routes.webhooks import IngestOut
from oryn.core.tenancy import Role
from oryn.orchestration.client import temporal_client
from oryn.services.ingest import ingest_event
from oryn.services.traffic import get_flag, set_flag

router = APIRouter(prefix="/api/simulate", tags=["simulate"])


class SimEventIn(BaseModel):
    type: str = Field(pattern=r"^[a-z_]+\.[a-z_]+$")
    payload: dict[str, Any] = {}


class TrafficIn(BaseModel):
    enabled: bool
    rate_per_min: int = Field(4, ge=1, le=30)


@router.post("/events", status_code=202, response_model=IngestOut)
async def fire_event(
    body: SimEventIn,
    ctx: TenantContext = Depends(require_role(Role.operator)),
    client: Client = Depends(temporal_client),
) -> IngestOut:
    r = await ingest_event(
        client,
        ctx.tenant_id,
        body.type,
        "simulator",
        body.payload,
        f"sim:{uuid.uuid4()}",
        started_by_user_id=ctx.user_id,
    )
    return IngestOut(event_id=str(r.event_id), created=r.created, run_ids=[str(x) for x in r.run_ids])


@router.get("/traffic")
async def traffic(ctx: TenantContext = Depends(require_role(Role.viewer))) -> dict[str, Any]:
    return await get_flag(ctx.tenant_id)


@router.post("/traffic")
async def set_traffic(body: TrafficIn, ctx: TenantContext = Depends(require_role(Role.operator))) -> dict[str, Any]:
    return await set_flag(ctx.tenant_id, body.enabled, body.rate_per_min)
