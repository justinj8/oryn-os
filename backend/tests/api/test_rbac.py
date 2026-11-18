from oryn.core.tenancy import Role, role_at_least
from tests.factories import auth_headers, make_member, make_tenant


def test_role_ordering() -> None:
    assert role_at_least(Role.owner, Role.admin)
    assert role_at_least(Role.operator, Role.operator)
    assert not role_at_least(Role.viewer, Role.operator)


async def test_api_key_auth_resolves_tenant(client) -> None:
    a = await make_tenant("alpha")
    o = await make_member(a, Role.owner)
    r = await client.post("/api/api-keys", headers=auth_headers(o, a), json={"name": "ci"})
    assert r.status_code == 201
    key, key_id = r.json()["key"], r.json()["id"]
    assert key.startswith("oryn_")

    who = await client.get("/api/health/tenant", headers={"Authorization": f"Bearer {key}"})
    assert who.status_code == 200
    assert who.json()["tenant_id"] == str(a.id)

    assert (await client.delete(f"/api/api-keys/{key_id}", headers=auth_headers(o, a))).status_code == 204
    again = await client.get("/api/health/tenant", headers={"Authorization": f"Bearer {key}"})
    assert again.status_code == 401


async def test_list_keys_never_returns_secret(client) -> None:
    a = await make_tenant("alpha")
    o = await make_member(a, Role.owner)
    await client.post("/api/api-keys", headers=auth_headers(o, a), json={"name": "ci"})
    rows = (await client.get("/api/api-keys", headers=auth_headers(o, a))).json()
    assert "key" not in rows[0] and "key_hash" not in rows[0]
