from sqlalchemy import select

from oryn.core.db import owner_session
from oryn.core.tenancy import Role
from oryn.models import Agent, AgentRole
from tests.factories import auth_headers, make_member
from tests.orchestration.wf_helpers import worker


async def _key(api, tenant) -> str:
    o = await make_member(tenant, Role.owner)
    return (await api.post("/api/api-keys", headers=auth_headers(o, tenant), json={"name": "sdk"})).json()["key"]


async def _agent_id(role: AgentRole):
    async with owner_session() as s:
        return (await s.execute(select(Agent.id).where(Agent.role == role))).scalar_one()


async def test_invoke_requires_api_key(api, tenant) -> None:
    r = await api.post(f"/v1/agents/{await _agent_id(AgentRole.support)}/invoke", json={"input": "hi"})
    assert r.status_code == 401


async def test_invoke_returns_reply_and_session(api, temporal_env, tenant, acts) -> None:
    key = await _key(api, tenant)
    aid = await _agent_id(AgentRole.support)
    async with worker(temporal_env.client, acts):
        r = await api.post(
            f"/v1/agents/{aid}/invoke",
            json={"input": "What is your refund policy?"},
            headers={"Authorization": f"Bearer {key}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok" and "30 days" in body["text"] and body["session_id"]
        again = await api.post(
            f"/v1/agents/{aid}/invoke",
            json={"input": "thanks!", "session_id": body["session_id"]},
            headers={"Authorization": f"Bearer {key}"},
        )
    assert again.json()["session_id"] == body["session_id"]


async def test_invoke_unknown_agent_404(api, tenant) -> None:
    import uuid

    key = await _key(api, tenant)
    r = await api.post(
        f"/v1/agents/{uuid.uuid4()}/invoke", json={"input": "hi"}, headers={"Authorization": f"Bearer {key}"}
    )
    assert r.status_code == 404
