"""Regression for a cross-tenant leak: db.query runs model/caller SQL, and a SELECT can call
set_config('app.tenant_id', ...) to switch tenants mid-transaction."""

import random

import pytest
from sqlalchemy import select

from oryn.connectors.errors import NonRetryableConnectorError
from oryn.connectors.faults import FaultInjector
from oryn.connectors.sandbox.database import SandboxDatabase
from oryn.core.db import owner_session, tenant_session
from oryn.models import SbContact
from tests.factories import make_tenant

ESCAPES = [
    "select * from (select set_config('app.tenant_id', '{b}', true)) q",
    "select set_config('app.tenant_id', '{b}', true) as x",
    "with f as materialized (select set_config('app.tenant_id', '{b}', true) x) "
    "select (select x from f), (select count(*) from sb_contacts)",
    "select pg_catalog.set_config('app.tenant_id', '{b}', true)",
    "select set_config('role', 'oryn_app', true)",
]


async def _tenants():
    a, b = await make_tenant("a"), await make_tenant("b")
    async with owner_session() as s:
        s.add(SbContact(tenant_id=b.id, name="Secret Customer", email="secret@b.example"))
    return a, b


@pytest.mark.parametrize("sql", ESCAPES)
async def test_db_query_cannot_switch_tenant(sql: str) -> None:
    a, b = await _tenants()
    async with tenant_session(a.id) as s:
        db = SandboxDatabase(s, a.id, FaultInjector(0, 0, random.Random(1)))
        with pytest.raises(NonRetryableConnectorError):
            await db.query(sql.format(b=b.id), {})
        # and the rest of the step still sees only tenant A
        assert (await s.execute(select(SbContact))).scalars().all() == []


@pytest.mark.parametrize(
    "sql",
    [
        "select email, password_hash from users",
        "select * from tenants",
        "select * from user_memberships('00000000-0000-0000-0000-000000000000')",
        "select * from api_keys",
    ],
)
async def test_db_query_cannot_read_platform_tables(sql: str) -> None:
    a, _ = await _tenants()
    async with tenant_session(a.id) as s:
        db = SandboxDatabase(s, a.id, FaultInjector(0, 0, random.Random(1)))
        with pytest.raises(NonRetryableConnectorError):
            await db.query(sql, {})


async def test_db_query_has_a_statement_timeout() -> None:
    a, _ = await _tenants()
    async with tenant_session(a.id) as s:
        db = SandboxDatabase(s, a.id, FaultInjector(0, 0, random.Random(1)))
        with pytest.raises(NonRetryableConnectorError, match=r"timeout|canceling"):
            await db.query("select pg_sleep(10)", {})


async def test_db_query_still_answers_business_questions() -> None:
    a, _ = await _tenants()
    async with owner_session() as s:
        s.add(SbContact(tenant_id=a.id, name="Mine", email="m@a.example"))
    async with tenant_session(a.id) as s:
        db = SandboxDatabase(s, a.id, FaultInjector(0, 0, random.Random(1)))
        res = await db.query("select name from sb_contacts", {})
    assert res.rows == [["Mine"]]
