import os

os.environ["ENV"] = "test"
os.environ.setdefault("DATABASE_URL_APP", "postgresql+asyncpg://oryn_app:oryn_app@localhost:55432/oryn_test")
os.environ.setdefault("DATABASE_URL_OWNER", "postgresql+asyncpg://oryn_owner:oryn_owner@localhost:55432/oryn_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:56379/15")
os.environ["TEMPORAL_TASK_QUEUE"] = "test-q"

import contextlib

import pytest
from sqlalchemy import text

from tests.dbutil import migrate_fresh, truncate_all
from tests.world import acts, invoice, run_row, tenant  # noqa: F401  (shared fixtures)


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    migrate_fresh()


@pytest.fixture(autouse=True)
async def _clean_db() -> None:
    await truncate_all()
    yield


@pytest.fixture(autouse=True)
async def _terminate_workflows(request):
    """Terminate whatever workflows a test left running. The time-skipping test server can't
    fast-forward time while any workflow has an unprocessed task, so leftovers would stall
    later tests that rely on time skipping."""
    yield
    if not {"temporal_env", "api"} & set(request.fixturenames):
        return
    from sqlalchemy import select

    from oryn.core.db import owner_session
    from oryn.models import Run

    env = request.getfixturevalue("temporal_env")
    async with owner_session() as s:
        ids = (await s.execute(select(Run.temporal_workflow_id))).scalars().all()
    for wf_id in ids:
        with contextlib.suppress(Exception):
            await env.client.get_workflow_handle(wf_id).terminate("test teardown")


@pytest.fixture(autouse=True)
def _isolated_task_queue():
    """Each test gets its own Temporal task queue, so long-lived workflows (conversations) left
    over from one test are never picked up by the next test's worker."""
    import uuid

    from oryn.core.config import get_settings

    s = get_settings()
    s.temporal_task_queue = f"test-{uuid.uuid4().hex[:8]}"
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
