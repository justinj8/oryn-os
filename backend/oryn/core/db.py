"""Database engines and tenant-scoped sessions.

Tenant isolation is enforced by Postgres row-level security, not by application filters.
Every runtime session connects as ``oryn_app`` (no BYPASSRLS) and sets
``app.tenant_id`` for the duration of its transaction via ``set_config(..., is_local=true)``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from oryn.core.config import get_settings

_engines: dict[str, AsyncEngine] = {}

# Pools: "app" serves request handlers and agent steps (which hold a connection for a whole
# step); "spans" serves trace writes, which commit independently *while* a step is open.
# Keeping them apart means trace writes can never starve waiting on connections held by steps.
_POOLS = {"app": (20, 10), "spans": (5, 10), "owner": (5, 5)}


def _engine(kind: str) -> AsyncEngine:
    if kind not in _engines:
        s = get_settings()
        url = s.database_url_owner if kind == "owner" else s.database_url_app
        size, overflow = _POOLS[kind]
        _engines[kind] = create_async_engine(url, pool_pre_ping=True, pool_size=size, max_overflow=overflow)
    return _engines[kind]


def app_engine() -> AsyncEngine:
    return _engine("app")


def owner_engine() -> AsyncEngine:
    return _engine("owner")


async def dispose_engines() -> None:
    for e in list(_engines.values()):
        await e.dispose()
    _engines.clear()


@asynccontextmanager
async def tenant_session(tenant_id: UUID, pool: Literal["app", "spans"] = "app") -> AsyncIterator[AsyncSession]:
    """A transaction in which RLS restricts every query to ``tenant_id``."""
    async with AsyncSession(_engine(pool), expire_on_commit=False) as session, session.begin():
        await session.execute(text("select set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)})
        yield session


@asynccontextmanager
async def system_session() -> AsyncIterator[AsyncSession]:
    """Runtime role with no tenant set: only global tables (tenants, users) are visible."""
    async with AsyncSession(app_engine(), expire_on_commit=False) as session, session.begin():
        yield session


@asynccontextmanager
async def owner_session() -> AsyncIterator[AsyncSession]:
    """Privileged role that bypasses RLS. Migrations, seed data and tests only."""
    async with AsyncSession(owner_engine(), expire_on_commit=False) as session, session.begin():
        yield session
