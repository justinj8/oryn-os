import random

from sqlalchemy import select

from oryn.core.db import owner_session
from oryn.core.tenancy import Role
from oryn.models import Agent, AgentRole, AuditLog, Connector, Run, SbContact
from oryn.services.traffic import TrafficGenerator
from tests.factories import auth_headers, make_member, make_tenant
from tests.orchestration.wf_helpers import GOLDEN
from tests.workflow_factory import make_workflow


async def test_agent_crud_and_invalid_tool_422(client, tenant) -> None:
    admin = await make_member(tenant, Role.admin)
    h = auth_headers(admin, tenant)
    agents = (await client.get("/api/agents", headers=h)).json()
    assert {a["role"] for a in agents} >= {"sales", "scheduler"}
    sales = next(a for a in agents if a["role"] == "sales")
    bad = await client.patch(f"/api/agents/{sales['id']}", headers=h, json={"allowed_tools": ["crm.nuke_everything"]})
    assert bad.status_code == 422
    ok = await client.patch(
        f"/api/agents/{sales['id']}", headers=h, json={"autonomy": "suggest", "allowed_tools": ["crm.*", "docs.search"]}
    )
    assert ok.status_code == 200 and ok.json()["autonomy"] == "suggest"
    created = await client.post(
        "/api/agents", headers=h, json={"name": "Ops Bot", "role": "ops", "allowed_tools": ["billing.*"]}
    )
    assert created.status_code == 201
    tools = (await client.get("/api/tools", headers=h)).json()
    assert any(t["name"] == "billing.issue_refund" and t["risk"] == "high" for t in tools)


async def test_operator_cannot_edit_agent(client, tenant) -> None:
    op = await make_member(tenant, Role.operator)
    async with owner_session() as s:
        aid = (await s.execute(select(Agent.id).where(Agent.role == AgentRole.sales))).scalar_one()
    r = await client.patch(f"/api/agents/{aid}", headers=auth_headers(op, tenant), json={"enabled": False})
    assert r.status_code == 403


async def test_connector_patch_audited_and_secrets_hidden(client, tenant) -> None:
    admin = await make_member(tenant, Role.admin)
    h = auth_headers(admin, tenant)
    async with owner_session() as s:
        c = (await s.execute(select(Connector))).scalar_one()
        c.config_encrypted = b"secret"
    conns = (await client.get("/api/connectors", headers=h)).json()
    assert "config_encrypted" not in conns[0] and conns[0]["has_secrets"] is True
    r = await client.patch(
        f"/api/connectors/{conns[0]['id']}", headers=h, json={"settings": {"failure_rate": 0.2, "latency_ms": 100}}
    )
    assert r.status_code == 200 and r.json()["settings"]["failure_rate"] == 0.2
    bad = await client.patch(f"/api/connectors/{conns[0]['id']}", headers=h, json={"settings": {"failure_rate": 3}})
    assert bad.status_code == 422
    async with owner_session() as s:
        assert "connector.updated" in (await s.execute(select(AuditLog.action))).scalars().all()


async def test_sandbox_contacts_scoped(client, tenant) -> None:
    other = await make_tenant("other")
    async with owner_session() as s:
        s.add(SbContact(tenant_id=tenant.id, name="Mine", email="m@x.com"))
        s.add(SbContact(tenant_id=other.id, name="Theirs", email="t@x.com"))
    v = await make_member(tenant, Role.viewer)
    rows = (await client.get("/api/sandbox/contacts", headers=auth_headers(v, tenant))).json()
    assert [r["name"] for r in rows["items"]] == ["Mine"]
    assert (await client.get("/api/sandbox/nope", headers=auth_headers(v, tenant))).status_code == 404


async def test_simulate_event_starts_run(api, temporal_env, tenant, acts) -> None:
    from tests.orchestration.wf_helpers import worker

    await make_workflow(tenant, GOLDEN)
    op = await make_member(tenant, Role.operator)
    async with worker(temporal_env.client, acts):
        r = await api.post(
            "/api/simulate/events",
            headers=auth_headers(op, tenant),
            json={"type": "lead.created", "payload": {"name": "Sam", "email": "sam@x.com", "budget_usd": 9000}},
        )
    assert r.status_code == 202 and len(r.json()["run_ids"]) == 1
    async with owner_session() as s:
        run = (await s.execute(select(Run))).scalar_one()
    assert run.started_by_user_id == op.id


async def test_traffic_flag_roundtrip(client, tenant) -> None:
    op = await make_member(tenant, Role.operator)
    h = auth_headers(op, tenant)
    r = await client.post("/api/simulate/traffic", headers=h, json={"enabled": True, "rate_per_min": 6})
    assert r.json() == {"enabled": True, "rate_per_min": 6}
    assert (await client.get("/api/simulate/traffic", headers=h)).json()["enabled"] is True
    assert (
        await client.post("/api/simulate/traffic", headers=h, json={"enabled": True, "rate_per_min": 500})
    ).status_code == 422
    await client.post("/api/simulate/traffic", headers=h, json={"enabled": False, "rate_per_min": 6})


def test_traffic_generator_deterministic() -> None:
    a = [TrafficGenerator(random.Random(3)).event(["lead.created", "ticket.created"]) for _ in range(1)]
    b = [TrafficGenerator(random.Random(3)).event(["lead.created", "ticket.created"]) for _ in range(1)]
    assert a == b
    ev_type, payload = TrafficGenerator(random.Random(5)).event(["lead.created"])
    assert ev_type == "lead.created" and payload["email"].endswith("@example.com") and payload["budget_usd"] > 0
