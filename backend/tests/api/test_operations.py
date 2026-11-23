"""Operator features: period comparison, re-running a run, the activity feed and system status."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from oryn.core.db import owner_session
from oryn.core.tenancy import Role
from oryn.models import Approval, ApprovalStatus, AuditLog, Event, Outcome, OutcomeType, Run, RunStatus
from tests.factories import auth_headers, make_member
from tests.orchestration.wf_helpers import GOLDEN, LEAD, worker
from tests.workflow_factory import make_workflow


async def _run(tenant, title="Lead: Dana", status=RunStatus.completed, days_ago: float = 0, **kw) -> uuid.UUID:
    rid = uuid.uuid4()
    start = datetime.now(UTC) - timedelta(days=days_ago)
    async with owner_session() as s:
        s.add(
            Run(
                id=rid,
                tenant_id=tenant.id,
                title=title,
                status=status,
                temporal_workflow_id=f"t-{rid}",
                started_at=start,
                ended_at=start + timedelta(seconds=30) if status != RunStatus.running else None,
                **kw,
            )
        )
    return rid


# ---- period over period -------------------------------------------------------------------------


async def test_overview_reports_the_previous_period_for_comparison(api, tenant) -> None:
    now_run = await _run(tenant, days_ago=2)
    await _run(tenant, days_ago=3)
    await _run(tenant, days_ago=4, status=RunStatus.failed)
    await _run(tenant, days_ago=35)
    await _run(tenant, days_ago=40, status=RunStatus.failed)
    await _run(tenant, days_ago=70)  # outside both windows
    async with owner_session() as s:
        s.add(
            Outcome(
                tenant_id=tenant.id,
                run_id=now_run,
                type=OutcomeType.meeting_booked,
                value_usd=Decimal("8200"),
                minutes_saved=30,
                occurred_at=datetime.now(UTC) - timedelta(days=2),
                idempotency_key="o1",
            )
        )
    viewer = await make_member(tenant, Role.viewer)
    body = (await api.get("/api/metrics/overview", params={"range": 30}, headers=auth_headers(viewer, tenant))).json()
    assert body["runs_total"] == 3
    assert body["outcomes_value_usd"] == 8200
    prev = body["previous"]
    assert prev["runs_total"] == 2
    assert prev["completion_rate"] == 0.5
    assert prev["outcomes_value_usd"] == 0
    assert prev["previous"] is None  # one level only


async def test_previous_period_can_be_skipped(api, tenant) -> None:
    viewer = await make_member(tenant, Role.viewer)
    r = await api.get("/api/metrics/overview", params={"compare": "false"}, headers=auth_headers(viewer, tenant))
    assert r.status_code == 200 and r.json()["previous"] is None


# ---- re-run -----------------------------------------------------------------------------------


async def _fire_lead(api, tenant, op) -> list[str]:
    r = await api.post(
        "/api/simulate/events", json={"type": "lead.created", "payload": LEAD}, headers=auth_headers(op, tenant)
    )
    assert r.status_code == 202, r.text
    return r.json()["run_ids"]


async def test_rerun_starts_only_the_same_workflow_from_the_original_event(api, tenant, temporal_env, acts) -> None:
    wf_a = await make_workflow(tenant, GOLDEN)
    await make_workflow(tenant, {**GOLDEN, "name": "Second listener"})
    op = await make_member(tenant, Role.operator)
    async with worker(temporal_env.client, acts):
        run_ids = await _fire_lead(api, tenant, op)
        assert len(run_ids) == 2  # both workflows listen to lead.created
        async with owner_session() as s:
            original = (
                await s.execute(select(Run).where(Run.id.in_([uuid.UUID(x) for x in run_ids]), Run.workflow_id == wf_a))
            ).scalar_one()
            original.status, original.ended_at = RunStatus.failed, datetime.now(UTC)
            original.error = "connector outage"

        r = await api.post(f"/api/runs/{original.id}/rerun", headers=auth_headers(op, tenant))
        assert r.status_code == 202, r.text
        new_ids = r.json()["run_ids"]
        assert len(new_ids) == 1
        async with owner_session() as s:
            new = await s.get(Run, uuid.UUID(new_ids[0]))
            event = await s.get(Event, new.trigger_event_id)
            first_event = await s.get(Event, original.trigger_event_id)
            audit = (await s.execute(select(AuditLog).where(AuditLog.action == "run.rerun"))).scalar_one()
        assert new.workflow_id == wf_a and new.id != original.id
        assert new.title == original.title
        assert new.started_by_user_id == op.id  # so the operator can't approve their own re-run
        assert event.source == "rerun" and event.payload == first_event.payload
        assert audit.target_id == original.id and audit.after == {"new_run_ids": new_ids}


async def test_rerun_is_idempotent_per_key(api, tenant, temporal_env, acts) -> None:
    await make_workflow(tenant, GOLDEN)
    op = await make_member(tenant, Role.operator)
    async with worker(temporal_env.client, acts):
        [rid] = await _fire_lead(api, tenant, op)
        async with owner_session() as s:
            run = await s.get(Run, uuid.UUID(rid))
            run.status, run.ended_at = RunStatus.failed, datetime.now(UTC)
        h = {**auth_headers(op, tenant), "Idempotency-Key": "click-1"}
        first = (await api.post(f"/api/runs/{rid}/rerun", headers=h)).json()["run_ids"]
        second = (await api.post(f"/api/runs/{rid}/rerun", headers=h)).json()["run_ids"]
        assert first == second and len(first) == 1


async def test_rerun_refuses_runs_still_in_flight(api, tenant) -> None:
    rid = await _run(tenant, status=RunStatus.running)
    op = await make_member(tenant, Role.operator)
    r = await api.post(f"/api/runs/{rid}/rerun", headers=auth_headers(op, tenant))
    assert r.status_code == 409


async def test_rerun_needs_a_triggering_event(api, tenant) -> None:
    rid = await _run(tenant, status=RunStatus.completed)  # e.g. a conversation: no event to replay
    op = await make_member(tenant, Role.operator)
    r = await api.post(f"/api/runs/{rid}/rerun", headers=auth_headers(op, tenant))
    assert r.status_code == 422


async def test_viewers_cannot_rerun(api, tenant) -> None:
    rid = await _run(tenant, status=RunStatus.failed)
    viewer = await make_member(tenant, Role.viewer)
    assert (await api.post(f"/api/runs/{rid}/rerun", headers=auth_headers(viewer, tenant))).status_code == 403


# ---- activity feed ----------------------------------------------------------------------------


async def test_activity_lists_what_needs_attention_newest_first(api, tenant) -> None:
    failed = await _run(tenant, title="Ticket: Ann", status=RunStatus.failed, days_ago=0.02, error="refund > balance")
    escalated = await _run(tenant, title="Ticket: Lee", status=RunStatus.escalated, days_ago=0.03)
    booked = await _run(tenant, title="Lead: Dana", days_ago=0.05)
    await _run(tenant, title="Lead: quiet success", days_ago=0.01)  # completed without an outcome: not news
    async with owner_session() as s:
        s.add(
            Outcome(
                tenant_id=tenant.id,
                run_id=booked,
                type=OutcomeType.meeting_booked,
                value_usd=Decimal("8200"),
                occurred_at=datetime.now(UTC) - timedelta(days=0.04),
                idempotency_key="o-dana",
            )
        )
        s.add(
            Approval(
                tenant_id=tenant.id,
                run_id=booked,
                step_id="qualify",
                description="Apply a 15.0% discount",
                idempotency_key="a1",
                risk_reasons=[],
                min_role=Role.operator,
                status=ApprovalStatus.pending,
                requested_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
    viewer = await make_member(tenant, Role.viewer)
    items = (await api.get("/api/activity", headers=auth_headers(viewer, tenant))).json()
    kinds = [i["kind"] for i in items]
    assert kinds == ["approval_requested", "run_failed", "run_escalated", "outcome"]
    assert items[1]["href"] == f"/runs/{failed}" and items[1]["detail"] == "refund > balance"
    assert items[2]["href"] == f"/runs/{escalated}"
    assert items[3]["title"] == "Meeting booked" and items[3]["value_usd"] == 8200
    times = [i["at"] for i in items]
    assert times == sorted(times, reverse=True)


async def test_activity_is_paged_by_time(api, tenant) -> None:
    for i in range(5):
        await _run(tenant, title=f"fail {i}", status=RunStatus.failed, days_ago=0.01 * (i + 1))
    viewer = await make_member(tenant, Role.viewer)
    h = auth_headers(viewer, tenant)
    first = (await api.get("/api/activity", params={"limit": 2}, headers=h)).json()
    rest = (await api.get("/api/activity", params={"limit": 10, "before": first[-1]["at"]}, headers=h)).json()
    assert [x["title"] for x in first] == ["fail 0", "fail 1"]
    assert [x["title"] for x in rest] == ["fail 2", "fail 3", "fail 4"]


# ---- system status ----------------------------------------------------------------------------


async def test_system_status_checks_every_dependency(api, tenant, temporal_env, acts) -> None:
    viewer = await make_member(tenant, Role.viewer)
    async with worker(temporal_env.client, acts):
        body = (await api.get("/api/system/status", headers=auth_headers(viewer, tenant))).json()
    checks = {c["name"]: c for c in body["checks"]}
    assert set(checks) == {"Database", "Redis", "Temporal", "Workers"}
    assert checks["Database"]["ok"] and checks["Redis"]["ok"] and checks["Temporal"]["ok"]
    assert all(isinstance(c["latency_ms"], (int, float)) for c in body["checks"])
    assert body["ok"] is all(c["ok"] for c in body["checks"])


async def test_runs_say_whether_they_can_be_rerun(api, tenant) -> None:
    plain = await _run(tenant, title="no event")
    viewer = await make_member(tenant, Role.viewer)
    body = (await api.get(f"/api/runs/{plain}", headers=auth_headers(viewer, tenant))).json()
    assert body["rerunnable"] is False
