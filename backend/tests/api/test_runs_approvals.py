import uuid

from sqlalchemy import select

from oryn.core.db import owner_session
from oryn.core.tenancy import Role
from oryn.models import Approval, AuditLog, Run, RunStatus
from tests.factories import auth_headers, make_member, make_tenant
from tests.orchestration.wf_helpers import GOLDEN, LEAD, wait_state, worker
from tests.workflow_factory import make_workflow


async def _api_key(api, tenant) -> str:
    owner = await make_member(tenant, Role.owner)
    return (await api.post("/api/api-keys", headers=auth_headers(owner, tenant), json={"name": "x"})).json()["key"]


async def _fire(api, tenant, key="evt-1") -> dict:
    api_key = await _api_key(api, tenant)
    r = await api.post(
        f"/api/webhooks/{tenant.slug}/events/lead.created",
        json=LEAD,
        headers={"Authorization": f"Bearer {api_key}", "Idempotency-Key": key},
    )
    assert r.status_code == 202, r.text
    return r.json()


async def test_webhook_requires_idempotency_key(api, tenant) -> None:
    api_key = await _api_key(api, tenant)
    r = await api.post(
        f"/api/webhooks/{tenant.slug}/events/lead.created", json=LEAD, headers={"Authorization": f"Bearer {api_key}"}
    )
    assert r.status_code == 400


async def test_webhook_key_must_match_tenant(api, tenant) -> None:
    other = await make_tenant("other")
    api_key = await _api_key(api, other)
    r = await api.post(
        f"/api/webhooks/{tenant.slug}/events/lead.created",
        json=LEAD,
        headers={"Authorization": f"Bearer {api_key}", "Idempotency-Key": "k"},
    )
    assert r.status_code == 403


async def test_get_foreign_run_404(api, tenant) -> None:
    other = await make_tenant("other")
    rid = uuid.uuid4()
    async with owner_session() as s:
        from datetime import UTC, datetime

        s.add(Run(id=rid, tenant_id=other.id, temporal_workflow_id=f"x-{rid}", started_at=datetime.now(UTC)))
    viewer = await make_member(tenant, Role.viewer)
    assert (await api.get(f"/api/runs/{rid}", headers=auth_headers(viewer, tenant))).status_code == 404


async def _pending(api, tenant, temporal_env, acts):
    await make_workflow(tenant, GOLDEN)
    fired = await _fire(api, tenant)
    from oryn.orchestration.run_workflow import OrynRunWorkflow

    async with owner_session() as s:
        run = await s.get(Run, uuid.UUID(fired["run_ids"][0]))
    h = temporal_env.client.get_workflow_handle_for(OrynRunWorkflow.run, run.temporal_workflow_id)
    await wait_state(h, "waiting_approval")
    async with owner_session() as s:
        approval = (await s.execute(select(Approval))).scalar_one()
    return h, approval, OrynRunWorkflow


async def test_decision_signals_workflow(api, tenant, temporal_env, acts) -> None:
    async with worker(temporal_env.client, acts):
        h, approval, _ = await _pending(api, tenant, temporal_env, acts)
        op = await make_member(tenant, Role.operator)
        listing = (await api.get("/api/approvals?status=pending", headers=auth_headers(op, tenant))).json()
        assert [a["id"] for a in listing] == [str(approval.id)]
        r = await api.post(
            f"/api/approvals/{approval.id}/decision",
            headers=auth_headers(op, tenant),
            json={"approved": True, "comment": "ok"},
        )
        assert r.status_code == 200, r.text
        res = await h.result()
    assert res.status == RunStatus.completed
    async with owner_session() as s:
        a = await s.get(Approval, approval.id)
        assert a.status == "approved" and a.decided_by == op.id
        assert "approval.approved" in (await s.execute(select(AuditLog.action))).scalars().all()
    spans = (await api.get(f"/api/runs/{a.run_id}/spans", headers=auth_headers(op, tenant))).json()
    assert any(sp["kind"] == "handoff" for sp in spans)


async def test_second_decision_returns_409(api, tenant, temporal_env, acts) -> None:
    async with worker(temporal_env.client, acts):
        h, approval, _ = await _pending(api, tenant, temporal_env, acts)
        op1, op2 = await make_member(tenant, Role.operator), await make_member(tenant, Role.admin)
        r1 = await api.post(
            f"/api/approvals/{approval.id}/decision", headers=auth_headers(op1, tenant), json={"approved": True}
        )
        r2 = await api.post(
            f"/api/approvals/{approval.id}/decision", headers=auth_headers(op2, tenant), json={"approved": False}
        )
        assert (r1.status_code, r2.status_code) == (200, 409)
        await h.result()


async def test_operator_cannot_approve_admin_level(api, tenant, temporal_env, acts) -> None:
    async with worker(temporal_env.client, acts):
        h, approval, wf = await _pending(api, tenant, temporal_env, acts)
        async with owner_session() as s:
            (await s.get(Approval, approval.id)).min_role = Role.admin
        op = await make_member(tenant, Role.operator)
        r = await api.post(
            f"/api/approvals/{approval.id}/decision", headers=auth_headers(op, tenant), json={"approved": True}
        )
        assert r.status_code == 403
        await h.signal(wf.cancel)
        await h.result()


async def test_runs_list_and_cancel(api, tenant, temporal_env, acts) -> None:
    async with worker(temporal_env.client, acts):
        h, approval, _ = await _pending(api, tenant, temporal_env, acts)
        op = await make_member(tenant, Role.operator)
        runs = (await api.get("/api/runs", headers=auth_headers(op, tenant))).json()
        assert runs["items"][0]["status"] == "waiting_approval"
        detail = (await api.get(f"/api/runs/{approval.run_id}", headers=auth_headers(op, tenant))).json()
        assert detail["live_state"]["pending_approval_id"] == str(approval.id)
        assert (
            await api.post(f"/api/runs/{approval.run_id}/cancel", headers=auth_headers(op, tenant))
        ).status_code == 202
        res = await h.result()
    assert res.status == RunStatus.cancelled
