import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from temporalio.client import Client

from oryn.api.deps import TenantContext, require_role
from oryn.api.routes.webhooks import IngestOut
from oryn.core.audit import record_audit
from oryn.core.db import tenant_session
from oryn.core.tenancy import Role
from oryn.models import Approval, Event, Outcome, Run, RunStatus, Span
from oryn.orchestration.client import temporal_client
from oryn.services.ingest import ingest_event

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
    route: list[str] = []  # agents that held the run, in order (Sales → Scheduler …)
    rerunnable: bool = False  # it came from an event and a workflow, so POST /rerun can replay it

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
            rerunnable=r.kind == "workflow" and r.trigger_event_id is not None and r.workflow_id is not None,
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
    q: str | None = Query(None, max_length=200, description="Case-insensitive match on the run title"),
    limit: int = 50,
    before: datetime | None = None,
    ctx: TenantContext = Depends(require_role(Role.viewer)),
) -> RunPage:
    limit = max(1, min(limit, 200))
    stmt = select(Run).order_by(Run.started_at.desc()).limit(limit + 1)
    if status_:
        stmt = stmt.where(Run.status == status_)
    if workflow_id:
        stmt = stmt.where(Run.workflow_id == workflow_id)
    if before:
        stmt = stmt.where(Run.started_at < before)
    if q and q.strip():
        stmt = stmt.where(title_matches(Run.title, q))
    async with tenant_session(ctx.tenant_id) as s:
        rows = (await s.execute(stmt)).scalars().all()
        routes = await _routes(s, [r.id for r in rows[:limit]])
    items = [RunOut.of(r).model_copy(update={"route": routes.get(r.id, [])}) for r in rows[:limit]]
    return RunPage(items=items, next_cursor=items[-1].started_at if len(rows) > limit else None)


def title_matches(column: Any, text: str) -> Any:
    """Substring match where %, _ and \\ in the user's text are literal characters, not wildcards."""
    escaped = text.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


@router.get("/runs/counts", response_model=dict[str, int])
async def run_counts(
    q: str | None = Query(None, max_length=200),
    ctx: TenantContext = Depends(require_role(Role.viewer)),
) -> dict[str, int]:
    """Runs per status (every status present, zero included) plus ``all``, for filter chips."""
    stmt = select(Run.status, func.count()).group_by(Run.status)
    if q and q.strip():
        stmt = stmt.where(title_matches(Run.title, q))
    async with tenant_session(ctx.tenant_id) as s:
        found = {st.value: n for st, n in (await s.execute(stmt)).all()}
    counts = {st.value: found.get(st.value, 0) for st in RunStatus}
    return {"all": sum(counts.values()), **counts}


async def _routes(s, run_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """Ordered, de-duplicated agent names per run, from its agent spans."""
    if not run_ids:
        return {}
    rows = await s.execute(
        select(Span.run_id, Span.name).where(Span.run_id.in_(run_ids), Span.kind == "agent").order_by(Span.started_at)
    )
    out: dict[uuid.UUID, list[str]] = {}
    for run_id, name in rows:
        agent = name.split(" · ")[0]
        route = out.setdefault(run_id, [])
        if not route or route[-1] != agent:
            route.append(agent)
    return out


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


@router.post("/runs/{run_id}/rerun", status_code=202, response_model=IngestOut)
async def rerun(
    run_id: uuid.UUID,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=100),
    ctx: TenantContext = Depends(require_role(Role.operator)),
    client: Client = Depends(temporal_client),
) -> IngestOut:
    """Start the run's workflow again from the event that started it, on the workflow's current version.

    The replay is a new event (source ``rerun``) under its own idempotency key, so a double click with
    the same ``Idempotency-Key`` starts one run, and the person re-running it counts as its starter:
    they can't approve its risky actions themselves.
    """
    async with tenant_session(ctx.tenant_id) as s:
        run = await _get_run(s, run_id)
        if run.status in (RunStatus.running, RunStatus.waiting_approval):
            raise HTTPException(status.HTTP_409_CONFLICT, f"run is still {run.status.value.replace('_', ' ')}")
        event = await s.get(Event, run.trigger_event_id) if run.trigger_event_id else None
        if run.kind != "workflow" or run.workflow_id is None or event is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "this run has no triggering event to replay")
        type_, payload, workflow_id = event.type, dict(event.payload), run.workflow_id

    result = await ingest_event(
        client,
        ctx.tenant_id,
        type_,
        "rerun",
        payload,
        f"rerun:{run_id}:{idempotency_key or uuid.uuid4()}",
        started_by_user_id=ctx.user_id,
        only_workflow_id=workflow_id,
    )
    if not result.run_ids:
        raise HTTPException(status.HTTP_409_CONFLICT, "the workflow is turned off or no longer matches this event")
    if result.created:
        async with tenant_session(ctx.tenant_id) as s:
            await record_audit(
                s, ctx, "run.rerun", "run", run_id, after={"new_run_ids": [str(x) for x in result.run_ids]}
            )
    return IngestOut(event_id=str(result.event_id), created=result.created, run_ids=[str(x) for x in result.run_ids])
