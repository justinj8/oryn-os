import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from oryn.core.db import owner_session, tenant_session
from oryn.core.tenancy import Role
from oryn.metrics.service import agent_leaderboard, overview, timeseries
from oryn.models import Agent, AgentRole, Approval, Outcome, OutcomeType, Run, RunStatus, Span, SpanKind
from tests.factories import auth_headers, make_member, make_tenant

NOW = datetime.now(UTC)


async def _run(t, status, dur_s=60, cost="0.01", ago_days=1, simulated=True) -> uuid.UUID:
    rid = uuid.uuid4()
    start = NOW - timedelta(days=ago_days)
    async with owner_session() as s:
        s.add(
            Run(
                id=rid,
                tenant_id=t.id,
                temporal_workflow_id=f"w{rid}",
                status=status,
                started_at=start,
                ended_at=start + timedelta(seconds=dur_s) if status != RunStatus.running else None,
                total_cost_usd=Decimal(cost),
                total_input_tokens=100,
                total_output_tokens=20,
                simulated_cost=simulated,
            )
        )
    return rid


async def test_completion_rate_excludes_running() -> None:
    t = await make_tenant("a")
    for st in [RunStatus.completed] * 3 + [RunStatus.failed, RunStatus.running, RunStatus.waiting_approval]:
        await _run(t, st)
    async with tenant_session(t.id) as s:
        m = await overview(s, 7)
    assert m.runs_total == 6 and m.runs_completed == 3 and m.failed == 1
    assert m.completion_rate == pytest.approx(0.75)


async def test_percentiles() -> None:
    t = await make_tenant("a")
    for d in range(1, 101):
        await _run(t, RunStatus.completed, dur_s=d)
    async with tenant_session(t.id) as s:
        m = await overview(s, 7)
    assert m.p50_duration_s == pytest.approx(50.5, abs=0.5)
    assert m.p95_duration_s == pytest.approx(95, abs=1)


async def test_roi_and_impact() -> None:
    t = await make_tenant("a", hourly_rate_usd=60)
    rid = await _run(t, RunStatus.completed, cost="2.00")
    async with owner_session() as s:
        s.add(
            Outcome(
                tenant_id=t.id,
                run_id=rid,
                type=OutcomeType.meeting_booked,
                value_usd=8200,
                minutes_saved=60,
                occurred_at=NOW - timedelta(hours=1),
            )
        )
        s.add(
            Outcome(
                tenant_id=t.id,
                run_id=rid,
                type=OutcomeType.ticket_resolved,
                value_usd=0,
                minutes_saved=60,
                occurred_at=NOW - timedelta(hours=1),
            )
        )
    async with tenant_session(t.id) as s:
        m = await overview(s, 7)
    assert m.meetings_booked == 1 and m.pipeline_usd == 8200 and m.tickets_resolved == 1
    assert m.minutes_saved == 120 and m.labor_savings_usd == pytest.approx(120.0)
    assert m.llm_cost_usd == pytest.approx(2.0) and m.roi_multiple == pytest.approx(60.0)
    assert m.simulated_cost is True


async def test_roi_none_without_cost() -> None:
    t = await make_tenant("a")
    async with tenant_session(t.id) as s:
        m = await overview(s, 7)
    assert m.runs_total == 0 and m.completion_rate is None and m.roi_multiple is None


async def test_approval_metrics_and_retry_rate() -> None:
    t = await make_tenant("a")
    r1, _r2 = await _run(t, RunStatus.completed), await _run(t, RunStatus.completed)
    async with owner_session() as s:
        s.add(
            Approval(
                tenant_id=t.id,
                run_id=r1,
                step_id="x",
                idempotency_key="a",
                min_role=Role.operator,
                status="approved",
                requested_at=NOW - timedelta(minutes=10),
                decided_at=NOW,
            )
        )
        s.add(
            Approval(
                tenant_id=t.id,
                run_id=r1,
                step_id="y",
                idempotency_key="b",
                min_role=Role.operator,
                status="pending",
                requested_at=NOW,
            )
        )
        s.add(Span(tenant_id=t.id, run_id=r1, kind=SpanKind.retry, name="retry", status="error", started_at=NOW))
    async with tenant_session(t.id) as s:
        m = await overview(s, 7)
    assert m.approvals_pending == 1 and m.avg_approval_wait_s == pytest.approx(600, abs=1)
    assert m.retry_rate == pytest.approx(0.5)


async def test_timeseries_zero_fills() -> None:
    t = await make_tenant("a")
    await _run(t, RunStatus.completed, ago_days=2)
    async with tenant_session(t.id) as s:
        pts = await timeseries(s, 7)
    assert len(pts) == 7
    assert sum(p.runs for p in pts) == 1 and sum(p.completed for p in pts) == 1
    assert pts[-1].day == NOW.date()


async def test_agent_leaderboard() -> None:
    t = await make_tenant("a")
    rid = await _run(t, RunStatus.completed)
    async with owner_session() as s:
        a = Agent(tenant_id=t.id, name="Sales", role=AgentRole.sales)
        s.add(a)
        await s.flush()
        s.add(
            Span(tenant_id=t.id, run_id=rid, agent_id=a.id, kind=SpanKind.agent, name="a", status="ok", started_at=NOW)
        )
        s.add(
            Span(
                tenant_id=t.id,
                run_id=rid,
                agent_id=a.id,
                kind=SpanKind.llm_call,
                name="m",
                status="ok",
                cost_usd=Decimal("0.03"),
                started_at=NOW,
            )
        )
    async with tenant_session(t.id) as s:
        rows = await agent_leaderboard(s, 7)
    assert rows[0].name == "Sales" and rows[0].runs == 1 and rows[0].cost_usd == pytest.approx(0.03)
    assert rows[0].completion_rate == 1.0


async def test_metrics_tenant_scoped(client) -> None:
    a, b = await make_tenant("a"), await make_tenant("b")
    await _run(b, RunStatus.completed)
    v = await make_member(a, Role.viewer)
    r = (await client.get("/api/metrics/overview?range=7", headers=auth_headers(v, a))).json()
    assert r["runs_total"] == 0
    assert (await client.get("/api/metrics/timeseries?range=30", headers=auth_headers(v, a))).status_code == 200
    assert (await client.get("/api/metrics/agents?range=30", headers=auth_headers(v, a))).status_code == 200
    _ = select
