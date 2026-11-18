import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from oryn.core.db import owner_session
from oryn.models import Event
from tests.factories import make_tenant


async def test_every_tenant_table_has_rls() -> None:
    async with owner_session() as s:
        tables = (
            (
                await s.execute(
                    text(
                        "select c.table_name from information_schema.columns c "
                        "where c.table_schema='public' and c.column_name='tenant_id'"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tables) >= 20
        for t in tables:
            row = (
                await s.execute(
                    text("select relrowsecurity, relforcerowsecurity from pg_class where relname=:t"),
                    {"t": t},
                )
            ).one()
            assert row == (True, True), t
            pol = (
                await s.execute(
                    text("select count(*) from pg_policies where tablename=:t and policyname='tenant_isolation'"),
                    {"t": t},
                )
            ).scalar_one()
            assert pol == 1, t


async def test_event_idempotency_unique() -> None:
    t = await make_tenant()
    with pytest.raises(IntegrityError):
        async with owner_session() as s:
            for _ in range(2):
                s.add(
                    Event(
                        id=uuid.uuid4(),
                        tenant_id=t.id,
                        type="lead.created",
                        source="web",
                        idempotency_key="k1",
                        payload={},
                    )
                )
                await s.flush()
