"""Run search, per-status counts and the command palette's search endpoint."""

import uuid
from datetime import UTC, datetime, timedelta

from oryn.core.db import owner_session
from oryn.core.tenancy import Role
from oryn.models import Approval, ApprovalStatus, Run, RunStatus
from tests.factories import auth_headers, make_member, make_tenant


async def _run(tenant, title: str, status: RunStatus = RunStatus.completed, minutes_ago: int = 0) -> uuid.UUID:
    rid = uuid.uuid4()
    async with owner_session() as s:
        s.add(
            Run(
                id=rid,
                tenant_id=tenant.id,
                title=title,
                status=status,
                temporal_workflow_id=f"t-{rid}",
                started_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
            )
        )
    return rid


async def test_runs_can_be_searched_by_title(api, tenant) -> None:
    await _run(tenant, "Lead: Dana Reyes")
    await _run(tenant, "Ticket: refund for Ann Lee")
    viewer = await make_member(tenant, Role.viewer)
    r = await api.get("/api/runs", params={"q": "dana"}, headers=auth_headers(viewer, tenant))
    assert r.status_code == 200
    assert [x["title"] for x in r.json()["items"]] == ["Lead: Dana Reyes"]


async def test_run_search_treats_wildcards_literally(api, tenant) -> None:
    await _run(tenant, "Discount 100% off")
    await _run(tenant, "Discount 15 off")
    viewer = await make_member(tenant, Role.viewer)
    r = await api.get("/api/runs", params={"q": "100%"}, headers=auth_headers(viewer, tenant))
    assert [x["title"] for x in r.json()["items"]] == ["Discount 100% off"]


async def test_run_counts_by_status(api, tenant) -> None:
    await _run(tenant, "a", RunStatus.completed)
    await _run(tenant, "b", RunStatus.completed)
    await _run(tenant, "c", RunStatus.failed)
    await _run(tenant, "d", RunStatus.waiting_approval)
    viewer = await make_member(tenant, Role.viewer)
    r = await api.get("/api/runs/counts", headers=auth_headers(viewer, tenant))
    assert r.status_code == 200
    body = r.json()
    assert body["all"] == 4
    assert body["completed"] == 2 and body["failed"] == 1 and body["waiting_approval"] == 1
    assert body["running"] == 0  # every status is present, so the UI never has to guess


async def test_run_counts_follow_the_search(api, tenant) -> None:
    await _run(tenant, "Lead: Dana", RunStatus.completed)
    await _run(tenant, "Lead: Sam", RunStatus.failed)
    await _run(tenant, "Ticket: Ann", RunStatus.failed)
    viewer = await make_member(tenant, Role.viewer)
    body = (await api.get("/api/runs/counts", params={"q": "lead"}, headers=auth_headers(viewer, tenant))).json()
    assert body["all"] == 2 and body["failed"] == 1


async def test_counts_and_search_stay_inside_the_tenant(api, tenant) -> None:
    other = await make_tenant("other")
    await _run(other, "Lead: someone else's")
    viewer = await make_member(tenant, Role.viewer)
    h = auth_headers(viewer, tenant)
    assert (await api.get("/api/runs/counts", headers=h)).json()["all"] == 0
    assert (await api.get("/api/search", params={"q": "lead"}, headers=h)).json() == []


async def test_search_finds_runs_and_pending_approvals(api, tenant) -> None:
    rid = await _run(tenant, "Lead: Dana Reyes", RunStatus.waiting_approval)
    async with owner_session() as s:
        s.add(
            Approval(
                tenant_id=tenant.id,
                run_id=rid,
                step_id="sales",
                action_tool="crm.apply_discount",
                action_args={"discount_pct": 15},
                description="Apply a 15.0% discount for Dana",
                risk_reasons=["over the 10% policy"],
                min_role=Role.admin,
                status=ApprovalStatus.pending,
                requested_at=datetime.now(UTC),
                idempotency_key=f"{rid}:sales:discount",
            )
        )
    viewer = await make_member(tenant, Role.viewer)
    hits = (await api.get("/api/search", params={"q": "dana"}, headers=auth_headers(viewer, tenant))).json()
    kinds = {h["kind"]: h for h in hits}
    assert kinds["run"]["href"] == f"/runs/{rid}"
    assert kinds["approval"]["href"] == "/approvals"
    assert kinds["approval"]["title"].startswith("Apply a 15.0% discount")


async def test_search_requires_a_query(api, tenant) -> None:
    viewer = await make_member(tenant, Role.viewer)
    r = await api.get("/api/search", params={"q": " "}, headers=auth_headers(viewer, tenant))
    assert r.status_code == 200 and r.json() == []
