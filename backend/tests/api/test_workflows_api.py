from oryn.core.tenancy import Role
from tests.builder.goldens import GOLDENS
from tests.factories import auth_headers, make_member


async def test_draft_then_save_then_version(client, tenant) -> None:
    admin = await make_member(tenant, Role.admin)
    h = auth_headers(admin, tenant)
    draft = (await client.post("/api/workflows/draft", headers=h, json={"text": GOLDENS[0][0]})).json()
    assert draft["errors"] == [] and draft["definition"]["trigger"]["event"] == "lead.created"
    r = await client.post(
        "/api/workflows", headers=h, json={"definition": draft["definition"], "source_text": GOLDENS[0][0]}
    )
    assert r.status_code == 201, r.text
    wid = r.json()["id"]
    assert r.json()["current_version"] == 1
    r2 = await client.post(f"/api/workflows/{wid}/versions", headers=h, json={"definition": GOLDENS[1][1]})
    assert r2.status_code == 201 and r2.json()["current_version"] == 2
    detail = (await client.get(f"/api/workflows/{wid}", headers=h)).json()
    assert [v["version"] for v in detail["versions"]] == [2, 1]
    assert detail["trigger_event"] == "ticket.created"
    off = await client.patch(f"/api/workflows/{wid}", headers=h, json={"enabled": False})
    assert off.json()["enabled"] is False


async def test_save_invalid_draft_rejected(client, tenant) -> None:
    admin = await make_member(tenant, Role.admin)
    bad = {
        "name": "x",
        "trigger": {"event": "e"},
        "steps": [{"id": "a", "type": "wait", "seconds": 5, "next": "nowhere"}],
    }
    r = await client.post("/api/workflows", headers=auth_headers(admin, tenant), json={"definition": bad})
    assert r.status_code == 422
    assert "unknown step 'nowhere'" in str(r.json()["detail"])


async def test_viewer_cannot_draft(client, tenant) -> None:
    v = await make_member(tenant, Role.viewer)
    r = await client.post("/api/workflows/draft", headers=auth_headers(v, tenant), json={"text": "When a lead"})
    assert r.status_code == 403


async def test_examples_compile(client, tenant) -> None:
    v = await make_member(tenant, Role.viewer)
    examples = (await client.get("/api/workflows/examples", headers=auth_headers(v, tenant))).json()
    assert len(examples) >= 5
