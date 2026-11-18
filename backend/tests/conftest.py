import os

os.environ["ENV"] = "test"
os.environ.setdefault("DATABASE_URL_APP", "postgresql+asyncpg://oryn_app:oryn_app@localhost:55432/oryn_test")
os.environ.setdefault("DATABASE_URL_OWNER", "postgresql+asyncpg://oryn_owner:oryn_owner@localhost:55432/oryn_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:56379/15")
os.environ["TEMPORAL_TASK_QUEUE"] = "test-q"

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


@pytest.fixture(scope="session")
async def temporal_env():
    from temporalio.contrib.pydantic import pydantic_data_converter
    from temporalio.testing import WorkflowEnvironment

    env = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    yield env
    await env.shutdown()


@pytest.fixture
async def api(temporal_env):
    """HTTP client whose app talks to the in-process Temporal test server."""
    from httpx import ASGITransport, AsyncClient

    from oryn.api.app import create_app
    from oryn.orchestration.client import temporal_client

    app = create_app()
    app.dependency_overrides[temporal_client] = lambda: temporal_env.client
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
