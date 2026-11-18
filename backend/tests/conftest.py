import os

os.environ["ENV"] = "test"
os.environ.setdefault("DATABASE_URL_APP", "postgresql+asyncpg://oryn_app:oryn_app@localhost:55432/oryn_test")
os.environ.setdefault(
    "DATABASE_URL_OWNER", "postgresql+asyncpg://oryn_owner:oryn_owner@localhost:55432/oryn_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:56379/15")

import pytest
from sqlalchemy import text

from tests.dbutil import migrate_fresh, truncate_all


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    migrate_fresh()


@pytest.fixture(autouse=True)
async def _clean_db() -> None:
    await truncate_all()
    yield


@pytest.fixture
def sql():
    return text


@pytest.fixture
async def client():
    from httpx import ASGITransport, AsyncClient

    from oryn.api.app import create_app

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        yield c
