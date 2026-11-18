import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from temporalio.client import Client

from oryn.api.deps import TenantContext, require_role
from oryn.api.routes.runs import ApprovalOut
from oryn.core.db import tenant_session
from oryn.core.tenancy import Role
from oryn.models import Approval, ApprovalStatus, Run
from oryn.orchestration.client import temporal_client
from oryn.services.approvals import DecisionError, decide

router = APIRouter(prefix="/api", tags=["approvals"])


class DecisionIn(BaseModel):
    approved: bool
    comment: str | None = None


@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    status: ApprovalStatus | None = None, limit: int = 100, ctx: TenantContext = Depends(require_role(Role.viewer))
) -> list[ApprovalOut]:
    q = (
        select(Approval, Run.title)
        .join(Run, Run.id == Approval.run_id)
        .order_by(Approval.requested_at.desc())
        .limit(min(limit, 500))
    )
    if status:
        q = q.where(Approval.status == status)
    async with tenant_session(ctx.tenant_id) as s:
        return [ApprovalOut.of(a, title) for a, title in await s.execute(q)]


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalOut)
async def decide_route(
    approval_id: uuid.UUID,
    body: DecisionIn,
    ctx: TenantContext = Depends(require_role(Role.operator)),
    client: Client = Depends(temporal_client),
) -> ApprovalOut:
    try:
        a = await decide(client, ctx, approval_id, body.approved, body.comment)
    except DecisionError as e:
        raise HTTPException(e.status_code, e.detail) from e
    return ApprovalOut.of(a)
