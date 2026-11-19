"""Temporal worker entrypoint: ``python -m oryn.orchestration.worker``."""

import asyncio

from temporalio.worker import Worker

from oryn.core.config import Settings, get_settings
from oryn.core.logging import configure_logging, log
from oryn.orchestration.activities import OrynActivities
from oryn.orchestration.client import get_temporal_client

# Each running agent step holds one 'app' pool connection (pool 20 + overflow 10), so keep
# concurrent activities under the pool size; extra work simply waits in Temporal's queue.
MAX_CONCURRENT_ACTIVITIES = 16
# History backfill gets its own queue and a small budget, so a person clicking around the demo never
# waits behind hundreds of seeded runs. 16 + 6 stays under the 'app' pool (20 + 10 overflow).
MAX_CONCURRENT_BACKFILL_ACTIVITIES = 6


def backfill_queue(settings: Settings) -> str:
    return settings.temporal_backfill_queue or f"{settings.temporal_task_queue}-backfill"


def workflows() -> list:
    from oryn.orchestration.run_workflow import OrynRunWorkflow

    wfs: list = [OrynRunWorkflow]
    try:
        from oryn.orchestration.conversation_workflow import ConversationWorkflow

        wfs.append(ConversationWorkflow)
    except ImportError:
        pass
    try:
        from oryn.orchestration.mcp_action_workflow import McpActionWorkflow

        wfs.append(McpActionWorkflow)
    except ImportError:
        pass
    return wfs


async def main() -> None:
    configure_logging()
    settings = get_settings()
    client = await get_temporal_client()
    acts = OrynActivities.default(settings)
    log.info("worker.start", task_queue=settings.temporal_task_queue, llm=settings.effective_llm_provider)
    background = []
    try:
        from oryn.services.traffic import traffic_loop

        background.append(asyncio.create_task(traffic_loop(client)))
    except ImportError:
        pass
    live = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=workflows(),
        activities=acts.all(),
        max_concurrent_activities=MAX_CONCURRENT_ACTIVITIES,
    )
    history = Worker(
        client,
        task_queue=backfill_queue(settings),
        workflows=workflows(),
        activities=acts.all(),
        max_concurrent_activities=MAX_CONCURRENT_BACKFILL_ACTIVITIES,
    )
    async with live, history:
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
