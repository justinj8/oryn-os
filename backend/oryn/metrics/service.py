"""Operational and business-impact metrics. Every number is derived from rows real runs wrote."""

import uuid
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import case, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from oryn.models import Agent, Approval, ApprovalStatus, Outcome, OutcomeType, Run, RunStatus, Span, SpanKind, Tenant

FINISHED = (RunStatus.completed, RunStatus.failed, RunStatus.escalated, RunStatus.cancelled)
DEFAULT_HOURLY_RATE = 45.0


class OverviewMetrics(BaseModel):
    range_days: int
    runs_total: int
    runs_completed: int
    completion_rate: float | None
    failed: int
    escalated: int
    in_flight: int
    p50_duration_s: float | None
    p95_duration_s: float | None
    llm_cost_usd: float
    cost_per_completed_run_usd: float | None
    tokens_in: int
    tokens_out: int
    simulated_cost: bool
    approvals_pending: int
    avg_approval_wait_s: float | None
    retry_rate: float | None
    meetings_booked: int
    pipeline_usd: float
    tickets_resolved: int
    invoices_collected_usd: float
    reports_delivered: int
    minutes_saved: int
    hourly_rate_usd: float
    labor_savings_usd: float
    roi_multiple: float | None


class TimeseriesPoint(BaseModel):
    day: date
    runs: int
    completed: int
    cost_usd: float
    outcomes_value_usd: float


class AgentLeaderboardRow(BaseModel):
    agent_id: uuid.UUID
    name: str
    role: str
    runs: int
    completion_rate: float | None
    cost_usd: float
    avg_llm_calls: float | None


def _since(range_days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=range_days)


async def _tenant_settings(s: AsyncSession) -> dict:
    tid = (await s.execute(text("select current_setting('app.tenant_id', true)"))).scalar()
    tenant = await s.get(Tenant, uuid.UUID(tid)) if tid else None
    return (tenant.settings or {}) if tenant else {}


async def overview(s: AsyncSession, range_days: int) -> OverviewMetrics:
    since = _since(range_days)
    in_window = Run.started_at >= since
    by_status = dict((await s.execute(select(Run.status, func.count()).where(in_window).group_by(Run.status))).all())
    total = sum(by_status.values())
    completed = by_status.get(RunStatus.completed, 0)
    finished = sum(by_status.get(x, 0) for x in FINISHED)

    duration = func.extract("epoch", Run.ended_at - Run.started_at)
    p50, p95 = (
        await s.execute(
            select(
                func.percentile_cont(0.5).within_group(duration), func.percentile_cont(0.95).within_group(duration)
            ).where(in_window, Run.status == RunStatus.completed)
        )
    ).one()
    cost, tin, tout, real_cost_runs = (
        await s.execute(
            select(
                func.coalesce(func.sum(Run.total_cost_usd), 0),
                func.coalesce(func.sum(Run.total_input_tokens), 0),
                func.coalesce(func.sum(Run.total_output_tokens), 0),
                func.count().filter(Run.simulated_cost.is_(False)),
            ).where(in_window)
        )
    ).one()
    pending = (
        await s.execute(select(func.count()).select_from(Approval).where(Approval.status == ApprovalStatus.pending))
    ).scalar_one()
    wait = (
        await s.execute(
            select(func.avg(func.extract("epoch", Approval.decided_at - Approval.requested_at))).where(
                Approval.decided_at.is_not(None), Approval.requested_at >= since
            )
        )
    ).scalar()
    retried = (
        await s.execute(
            select(func.count(distinct(Span.run_id)))
            .join(Run, Run.id == Span.run_id)
            .where(Span.kind == SpanKind.retry, in_window)
        )
    ).scalar_one()

    o = Outcome.occurred_at >= since
    agg = (
        await s.execute(
            select(
                func.count().filter(Outcome.type == OutcomeType.meeting_booked),
                func.coalesce(
                    func.sum(Outcome.value_usd).filter(
                        Outcome.type.in_([OutcomeType.meeting_booked, OutcomeType.deal_created])
                    ),
                    0,
                ),
                func.count().filter(Outcome.type == OutcomeType.ticket_resolved),
                func.coalesce(func.sum(Outcome.value_usd).filter(Outcome.type == OutcomeType.invoice_collected), 0),
                func.count().filter(Outcome.type == OutcomeType.report_delivered),
                func.coalesce(func.sum(Outcome.minutes_saved), 0),
            ).where(o)
        )
    ).one()
    meetings, pipeline, tickets, collected, reports, minutes = agg

    rate = float((await _tenant_settings(s)).get("hourly_rate_usd", DEFAULT_HOURLY_RATE))
    labor = minutes / 60 * rate
    cost_f = float(cost)
    return OverviewMetrics(
        range_days=range_days,
        runs_total=total,
        runs_completed=completed,
        completion_rate=completed / finished if finished else None,
        failed=by_status.get(RunStatus.failed, 0),
        escalated=by_status.get(RunStatus.escalated, 0),
        in_flight=by_status.get(RunStatus.running, 0) + by_status.get(RunStatus.waiting_approval, 0),
        p50_duration_s=float(p50) if p50 is not None else None,
        p95_duration_s=float(p95) if p95 is not None else None,
        llm_cost_usd=cost_f,
        cost_per_completed_run_usd=cost_f / completed if completed else None,
        tokens_in=int(tin),
        tokens_out=int(tout),
        simulated_cost=real_cost_runs == 0,
        approvals_pending=pending,
        avg_approval_wait_s=float(wait) if wait is not None else None,
        retry_rate=retried / total if total else None,
        meetings_booked=meetings,
        pipeline_usd=float(pipeline),
        tickets_resolved=tickets,
        invoices_collected_usd=float(collected),
        reports_delivered=reports,
        minutes_saved=int(minutes),
        hourly_rate_usd=rate,
        labor_savings_usd=labor,
        roi_multiple=labor / cost_f if cost_f > 0 else None,
    )


async def timeseries(s: AsyncSession, range_days: int) -> list[TimeseriesPoint]:
    today = datetime.now(UTC).date()
    days = [today - timedelta(days=i) for i in range(range_days - 1, -1, -1)]
    since = datetime.combine(days[0], datetime.min.time(), UTC)
    day_expr = func.date(func.timezone("UTC", Run.started_at))
    runs = {
        d: (n, c, cost)
        for d, n, c, cost in (
            await s.execute(
                select(
                    day_expr,
                    func.count(),
                    func.count().filter(Run.status == RunStatus.completed),
                    func.coalesce(func.sum(Run.total_cost_usd), 0),
                )
                .where(Run.started_at >= since)
                .group_by(day_expr)
            )
        ).all()
    }
    o_day = func.date(func.timezone("UTC", Outcome.occurred_at))
    values = dict(
        (
            await s.execute(
                select(o_day, func.coalesce(func.sum(Outcome.value_usd), 0))
                .where(Outcome.occurred_at >= since)
                .group_by(o_day)
            )
        ).all()
    )
    return [
        TimeseriesPoint(
            day=d,
            runs=runs.get(d, (0, 0, 0))[0],
            completed=runs.get(d, (0, 0, 0))[1],
            cost_usd=float(runs.get(d, (0, 0, 0))[2]),
            outcomes_value_usd=float(values.get(d, 0)),
        )
        for d in days
    ]


async def agent_leaderboard(s: AsyncSession, range_days: int) -> list[AgentLeaderboardRow]:
    since = _since(range_days)
    steps = (
        select(Span.agent_id, Span.run_id)
        .join(Run, Run.id == Span.run_id)
        .where(Span.kind == SpanKind.agent, Run.started_at >= since)
        .distinct()
        .subquery()
    )
    runs_q = (
        select(
            steps.c.agent_id,
            func.count(),
            func.count().filter(Run.status == RunStatus.completed),
            func.count().filter(Run.status.in_(FINISHED)),
        )
        .join(Run, Run.id == steps.c.run_id)
        .group_by(steps.c.agent_id)
    )
    run_stats = {a: (n, c, f) for a, n, c, f in (await s.execute(runs_q)).all()}
    llm = dict(
        (
            await s.execute(
                select(Span.agent_id, func.coalesce(func.sum(Span.cost_usd), 0))
                .join(Run, Run.id == Span.run_id)
                .where(Span.kind == SpanKind.llm_call, Run.started_at >= since)
                .group_by(Span.agent_id)
            )
        ).all()
    )
    calls = dict(
        (
            await s.execute(
                select(
                    Span.agent_id,
                    func.sum(case((Span.kind == SpanKind.llm_call, 1), else_=0))
                    / func.nullif(func.sum(case((Span.kind == SpanKind.agent, 1), else_=0)), 0),
                )
                .join(Run, Run.id == Span.run_id)
                .where(Run.started_at >= since)
                .group_by(Span.agent_id)
            )
        ).all()
    )
    agents = (await s.execute(select(Agent))).scalars().all()
    rows = []
    for a in agents:
        n, c, f = run_stats.get(a.id, (0, 0, 0))
        rows.append(
            AgentLeaderboardRow(
                agent_id=a.id,
                name=a.name,
                role=a.role.value,
                runs=n,
                completion_rate=c / f if f else None,
                cost_usd=float(llm.get(a.id, 0)),
                avg_llm_calls=float(calls[a.id]) if calls.get(a.id) is not None else None,
            )
        )
    return sorted(rows, key=lambda r: -r.runs)
