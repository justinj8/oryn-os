"""Test helpers for a real Postgres test database (oryn_test)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from oryn.core.config import get_settings
from oryn.core.db import owner_session

BACKEND = Path(__file__).resolve().parents[1]


def _sync_owner_url() -> str:
    return get_settings().database_url_owner.replace("+asyncpg", "+psycopg")


def migrate_fresh() -> None:
    eng = create_engine(_sync_owner_url(), isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text("DROP OWNED BY oryn_owner"))
    eng.dispose()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", _sync_owner_url())
    command.upgrade(cfg, "head")


async def truncate_all() -> None:
    async with owner_session() as s:
        rows = await s.execute(
            text("select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version'")
        )
        names = [r[0] for r in rows]
        if names:
            await s.execute(text(f"TRUNCATE {', '.join(names)} RESTART IDENTITY CASCADE"))
