from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from oryn.core.config import get_settings

_client: Client | None = None


async def get_temporal_client() -> Client:
    global _client
    if _client is None:
        s = get_settings()
        _client = await Client.connect(
            s.temporal_address, namespace=s.temporal_namespace, data_converter=pydantic_data_converter
        )
    return _client


async def temporal_client() -> Client:
    """FastAPI dependency (overridden in tests with the in-process test server)."""
    return await get_temporal_client()


def get_task_queue() -> str:
    return get_settings().temporal_task_queue
