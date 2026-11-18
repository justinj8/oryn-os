import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from temporalio.client import Client

from oryn.api.deps import TenantContext, require_role
from oryn.core.audit import record_audit
from oryn.core.db import tenant_session
from oryn.core.tenancy import Role
from oryn.models import Approval, Outcome, Run, RunStatus, Span
from oryn.orchestration.client import temporal_client

router = APIRouter(prefix="/api", tags=["runs"])


class RunOut(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    status: RunStatus
    workflow_id: uuid.UUID | None
    started_at: datetime
    ended_at: datetime | None
    duration_s: float | None
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: Decimal
    simulated_cost: bool
    outcome_summary: str | None
    error: str | None
    temporal_workflow_id: str

    @classmethod
    def of(cls, r: Run) -> "RunOut":
        return cls(
            id=r.id,
            title=r.title,
            kind=r.kind,
            status=r.status,
            workflow_id=r.workflow_id,
            started_at=r.started_at,
            ended_at=r.ended_at,
            duration_s=(r.ended_at - r.started_at).total_seconds() if r.ended_at else None,
            total_input_tokens=r.total_input_tokens,
            total_output_tokens=r.total_output_tokens,
            total_cost_usd=r.total_cost_usd,
            simulated_cost=r.simulated_cost,
            outcome_summary=r.outcome_summary,
            error=r.error,
            temporal_workflow_id=r.temporal_workflow_id,
        )


class RunPage(BaseModel):
    items: list[RunOut]
    next_cursor: datetime | None


class ApprovalOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    run_title: str | None = None
    step_id: str
    action_tool: str | None
    action_args: dict[str, Any]
    description: str
    risk_reasons: list[str]
    min_role: Role
    status: str
    requested_at: datetime
    expires_at: datetime | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    comment: str | None
    escalation_level: int

    @classmethod
    def of(cls, a: Approval, run_title: str | None = None) -> "ApprovalOut":
        return cls(
            id=a.id,
            run_id=a.run_id,
            run_title=run_title,
            step_id=a.step_id,
            action_tool=a.action_tool,
            action_args=a.action_args,
            description=a.description,
            risk_reasons=a.risk_reasons,
            min_role=a.min_role,
            status=a.status.value,
            requested_at=a.requested_at,
            expires_at=a.expires_at,
            decided_by=a.decided_by,
            decided_at=a.decided_at,
            comment=a.comment,
            escalation_level=a.escalation_level,
        )


class OutcomeOut(BaseModel):
    type: str
    value_usd: Decimal
    minutes_saved: int
    occurred_at: datetime


class RunDetail(RunOut):
    blackboard: dict[str, Any]
    approvals: list[ApprovalOut]
    outcomes: list[OutcomeOut]
    live_state: dict[str, Any] | None


class SpanOut(BaseModel):
    id: uuid.UUID
    parent_span_id: uuid.UUID | None
    agent_id: uuid.UUID | None
    kind: str
    name: str
    status: str
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    simulated: bool
    attempt: int
    started_at: datetime
    ended_at: datetime | None


@router.get("/runs", response_model=RunPage)
async def list_runs(
    status_: RunStatus | None = Query(None, alias="status"),
    workflow_id: uuid.UUID | None = None,
    limit: int = 50,
    before: datetime | None = None,
    ctx: TenantContext = Depends(require_role(Role.viewer)),
) -> RunPage:
    limit = max(1, min(limit, 200))
    q = select(Run).order_by(Run.started_at.desc()).limit(limit + 1)
    if status_:
        q = q.where(Run.status == status_)
    if workflow_id:
        q = q.where(Run.workflow_id == workflow_id)
    if before:
        q = q.where(Run.started_at < before)
    async with tenant_session(ctx.tenant_id) as s:
        rows = (await s.execute(q)).scalars().all()
    items = [RunOut.of(r) for r in rows[:limit]]
    return RunPage(items=items, next_cursor=items[-1].started_at if len(rows) > limit else None)


async def _get_run(s, run_id: uuid.UUID) -> Run:
    run = await s.get(Run, run_id)  # RLS: another tenant's run is simply not found
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return run


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(
    run_id: uuid.UUID,
    ctx: TenantContext = Depends(require_role(Role.viewer)),
    client: Client = Depends(temporal_client),
) -> RunDetail:
    async with tenant_session(ctx.tenant_id) as s:
        run = await _get_run(s, run_id)
        approvals = (
            (await s.execute(select(Approval).where(Approval.run_id == run_id).order_by(Approval.requested_at)))
            .scalars()
            .all()
        )
        outcomes = (await s.execute(select(Outcome).where(Outcome.run_id == run_id))).scalars().all()
    live = None
    if run.status in (RunStatus.running, RunStatus.waiting_approval) and run.kind == "workflow":
        try:
            st = await client.get_workflow_handle(run.temporal_workflow_id).query("get_state")
            live = st if isinstance(st, dict) else st.model_dump(mode="json")
        except Exception:
            live = None
    return RunDetail(
        **RunOut.of(run).model_dump(),
        blackboard=run.blackboard or {},
        approvals=[ApprovalOut.of(a) for a in approvals],
        outcomes=[
            OutcomeOut(
                type=o.type.value, value_usd=o.value_usd, minutes_saved=o.minutes_saved, occurred_at=o.occurred_at
            )
            for o in outcomes
        ],
        live_state=live,
    )


@router.get("/runs/{run_id}/spans", response_model=list[SpanOut])
async def get_spans(run_id: uuid.UUID, ctx: TenantContext = Depends(require_role(Role.viewer))) -> list[SpanOut]:
    async with tenant_session(ctx.tenant_id) as s:
        await _get_run(s, run_id)
        spans = (await s.execute(select(Span).where(Span.run_id == run_id).order_by(Span.started_at))).scalars()
        return [
            SpanOut(
                id=x.id,
                parent_span_id=x.parent_span_id,
                agent_id=x.agent_id,
                kind=x.kind.value,
                name=x.name,
                status=x.status,
                input=x.input,
                output=x.output,
                input_tokens=x.input_tokens,
                output_tokens=x.output_tokens,
                cost_usd=x.cost_usd,
                simulated=x.simulated,
                attempt=x.attempt,
                started_at=x.started_at,
                ended_at=x.ended_at,
            )
            for x in spans
        ]


@router.post("/runs/{run_id}/cancel", status_code=202)
async def cancel_run(
    run_id: uuid.UUID,
    ctx: TenantContext = Depends(require_role(Role.operator)),
    client: Client = Depends(temporal_client),
) -> dict[str, str]:
    async with tenant_session(ctx.tenant_id) as s:
        run = await _get_run(s, run_id)
        if run.status not in (RunStatus.running, RunStatus.waiting_approval):
            raise HTTPException(status.HTTP_409_CONFLICT, f"run is already {run.status.value}")
        await record_audit(s, ctx, "run.cancel_requested", "run", run_id)
        wf_id = run.temporal_workflow_id
    await client.get_workflow_handle(wf_id).signal("cancel")
    return {"status": "cancel_requested"}
