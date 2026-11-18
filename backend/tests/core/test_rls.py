import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from oryn.core.db import owner_session, system_session, tenant_session
from oryn.core.tenancy import Role
from oryn.models import Membership, Tenant, User


async def _two_tenants() -> tuple[uuid.UUID, uuid.UUID]:
    a, b = uuid.uuid4(), uuid.uuid4()
    async with owner_session() as s:
        s.add_all([Tenant(id=a, slug="a", name="A"), Tenant(id=b, slug="b", name="B")])
        u = User(email="u@x.test", name="U", password_hash="x")
        s.add(u)
        await s.flush()
        s.add_all(
            [
                Membership(tenant_id=a, user_id=u.id, role=Role.owner),
                Membership(tenant_id=b, user_id=u.id, role=Role.viewer),
            ]
        )
    return a, b


async def test_tenant_session_sees_only_own_rows() -> None:
    a, _ = await _two_tenants()
    async with tenant_session(a) as s:
        rows = (await s.execute(select(Membership))).scalars().all()
    assert [m.tenant_id for m in rows] == [a]


async def test_raw_sql_cannot_cross_tenants() -> None:
    a, b = await _two_tenants()
    async with tenant_session(a) as s:
        n = (
            await s.execute(text("select count(*) from memberships where tenant_id = :b"), {"b": b})
        ).scalar_one()
    assert n == 0


async def test_no_tenant_context_sees_nothing() -> None:
    await _two_tenants()
    async with system_session() as s:
        rows = (await s.execute(select(Membership))).scalars().all()
    assert rows == []


async def test_insert_with_foreign_tenant_id_rejected() -> None:
    a, b = await _two_tenants()
    with pytest.raises(DBAPIError):
        async with tenant_session(a) as s:
            user_id = (await s.execute(text("select id from users limit 1"))).scalar_one()
            s.add(Membership(tenant_id=b, user_id=user_id, role=Role.admin))
            await s.flush()
