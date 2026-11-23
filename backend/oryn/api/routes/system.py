"""System status: is every dependency reachable, how fast, and are workers picking up work.

``/api/health`` answers "is the API process up" for load balancers. This answers the question a
person asks when runs seem stuck: which part is down?
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest, GetSystemInfoRequest
from temporalio.client import Client

from oryn.api.deps import TenantContext, require_role
from oryn.core.config import get_settings
from oryn.core.db import tenant_session
from oryn.core.tenancy import Role
from oryn.observability.bus import get_event_bus
from oryn.orchestration.client import get_task_queue, temporal_client

router = APIRouter(prefix="/api/system", tags=["system"])
TIMEOUT_S = 2.0


class Check(BaseModel):
    name: str
    ok: bool
    latency_ms: float
    detail: str


class SystemStatus(BaseModel):
    ok: bool
    checks: list[Check]
    llm_provider: str
    checked_at: datetime


async def _check(name: str, probe: Callable[[], Awaitable[tuple[bool, str]]]) -> Check:
    start = time.perf_counter()
    try:
        ok, detail = await asyncio.wait_for(probe(), TIMEOUT_S)
    except TimeoutError:
        ok, detail = False, f"no answer within {TIMEOUT_S:g}s"
    except Exception as e:  # a status page must report failures, not raise them
        ok, detail = False, str(e) or type(e).__name__
    return Check(name=name, ok=ok, latency_ms=round((time.perf_counter() - start) * 1000, 1), detail=detail)


@router.get("/status", response_model=SystemStatus)
async def system_status(
    ctx: TenantContext = Depends(require_role(Role.viewer)),
    client: Client = Depends(temporal_client),
) -> SystemStatus:
    queue = get_task_queue()

    async def database() -> tuple[bool, str]:
        async with tenant_session(ctx.tenant_id) as s:
            await s.execute(text("select 1"))
        return True, "Postgres is answering queries"

    async def redis() -> tuple[bool, str]:
        await get_event_bus().redis.ping()
        return True, "Live updates can be delivered"

    async def temporal() -> tuple[bool, str]:
        await client.workflow_service.get_system_info(GetSystemInfoRequest())
        return True, f"Connected to namespace {client.namespace}"

    async def workers() -> tuple[bool, str]:
        resp = await client.workflow_service.describe_task_queue(
            DescribeTaskQueueRequest(
                namespace=client.namespace,
                task_queue=TaskQueue(name=queue),
                task_queue_type=TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW,
            )
        )
        n = len(resp.pollers)
        if n == 0:
            return False, f"No worker is polling {queue}: runs will wait until one starts"
        return True, f"{n} worker{'s' if n != 1 else ''} polling {queue}"

    checks = list(
        await asyncio.gather(
            _check("Database", database),
            _check("Redis", redis),
            _check("Temporal", temporal),
            _check("Workers", workers),
        )
    )
    return SystemStatus(
        ok=all(c.ok for c in checks),
        checks=checks,
        llm_provider=get_settings().effective_llm_provider,
        checked_at=datetime.now(UTC),
    )
