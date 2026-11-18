import pytest

from tests.orchestration.wf_helpers import worker


@pytest.fixture(autouse=True)
async def _worker(temporal_env, acts):
    """Ingest starts real workflows; keep a worker running so none is left with an unprocessed task."""
    async with worker(temporal_env.client, acts):
        yield
