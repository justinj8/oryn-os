"""Temporal worker entrypoint: ``python -m oryn.orchestration.worker``."""

import asyncio

from temporalio.worker import Worker

from oryn.core.config import get_settings
from oryn.core.logging import configure_logging, log
from oryn.orchestration.activities import OrynActivities
from oryn.orchestration.client import get_temporal_client

# Each running agent step holds one 'app' pool connection (pool 20 + overflow 10), so keep
# concurrent activities under the pool size; extra work simply waits in Temporal's queue.
MAX_CONCURRENT_ACTIVITIES = 20


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
    async with Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=workflows(),
        activities=acts.all(),
        max_concurrent_activities=50,
    ):
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
