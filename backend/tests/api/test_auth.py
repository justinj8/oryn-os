from sqlalchemy import select

from oryn.core.db import owner_session
from oryn.core.tenancy import Role
from oryn.models import AuditLog
from tests.factories import auth_headers, make_member, make_membership, make_tenant, make_user


async def test_login_success_returns_memberships(client) -> None:
    a, b = await make_tenant("alpha"), await make_tenant("beta")
    u = await make_user("pat@x.test", "s3cret")
    await make_membership(a, u, Role.owner)
    await make_membership(b, u, Role.viewer)
    r = await client.post("/api/auth/login", json={"email": "pat@x.test", "password": "s3cret"})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    roles = {m["slug"]: m["role"] for m in body["memberships"]}
    assert roles == {"alpha": "owner", "beta": "viewer"}


async def test_login_wrong_password_401(client) -> None:
    await make_user("pat@x.test", "s3cret")
    r = await client.post("/api/auth/login", json={"email": "pat@x.test", "password": "nope"})
    assert r.status_code == 401


async def test_me_requires_token(client) -> None:
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_foreign_tenant_header_forbidden(client) -> None:
    a, b = await make_tenant("alpha"), await make_tenant("beta")
    u = await make_member(a, Role.owner)
    r = await client.get("/api/members", headers=auth_headers(u, b))
    assert r.status_code == 403


async def test_viewer_cannot_manage_members(client) -> None:
    a = await make_tenant("alpha")
    v = await make_member(a, Role.viewer)
    r = await client.post(
        "/api/members",
        headers=auth_headers(v, a),
        json={"email": "n@x.test", "name": "N", "role": "operator"},
    )
    assert r.status_code == 403


async def test_owner_can_invite_member(client) -> None:
    a = await make_tenant("alpha")
    o = await make_member(a, Role.owner)
    r = await client.post(
        "/api/members",
        headers=auth_headers(o, a),
        json={"email": "new@x.test", "name": "New", "role": "operator", "password": "temp-pass-1"},
    )
    assert r.status_code == 201
    assert r.json()["role"] == "operator"
    async with owner_session() as s:
        actions = (await s.execute(select(AuditLog.action))).scalars().all()
    assert actions == ["member.created"]
