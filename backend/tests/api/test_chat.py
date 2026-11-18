import uuid

from tests.orchestration.wf_helpers import worker


async def test_chat_api_roundtrip(api, temporal_env, tenant, acts) -> None:
    async with worker(temporal_env.client, acts):
        sid = (await api.post(f"/api/chat/{tenant.slug}/sessions", json={})).json()["session_id"]
        r = await api.post(
            f"/api/chat/{tenant.slug}/sessions/{sid}/messages",
            json={"text": "hello there", "message_id": uuid.uuid4().hex},
        )
        assert r.status_code == 200 and r.json()["status"] == "ok"
        hist = (await api.get(f"/api/chat/{tenant.slug}/sessions/{sid}/messages")).json()
    assert [m["direction"] for m in hist] == ["in", "out"]


async def test_empty_message_rejected(api, tenant) -> None:
    sid = (await api.post(f"/api/chat/{tenant.slug}/sessions", json={})).json()["session_id"]
    r = await api.post(f"/api/chat/{tenant.slug}/sessions/{sid}/messages", json={"text": "  ", "message_id": "x"})
    assert r.status_code == 422


async def test_unknown_tenant_404(api) -> None:
    assert (await api.post("/api/chat/nope/sessions", json={})).status_code == 404
