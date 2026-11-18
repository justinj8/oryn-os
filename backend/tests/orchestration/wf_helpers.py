import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from temporalio.client import Client, WorkflowHandle
from temporalio.worker import Worker

from oryn.core.config import get_settings
from oryn.core.db import owner_session
from oryn.models import Run
from oryn.orchestration.activities import OrynActivities
from oryn.orchestration.conversation_workflow import ConversationWorkflow
from oryn.orchestration.mcp_action_workflow import McpActionWorkflow
from oryn.orchestration.models import RunInput, RunState
from oryn.orchestration.run_workflow import OrynRunWorkflow
from oryn.workflows.dsl import WorkflowDefinition


def tq() -> str:
    return get_settings().temporal_task_queue


LEAD = {
    "name": "Dana Reyes",
    "email": "dana@example.com",
    "phone": "+15550101",
    "company": "Reyes Co",
    "need": "heat pump install",
    "budget_usd": 8200,
    "requested_discount_pct": 15,
    "source": "web",
}
GOLDEN = {
    "name": "Inbound lead to booked meeting",
    "trigger": {"event": "lead.created"},
    "steps": [
        {"id": "qualify", "type": "agent", "role": "sales", "goal": "Qualify the lead and propose a quote"},
        {"id": "gate", "type": "condition", "if": "blackboard.qualified == true", "then": "end", "else": "nurture"},
        {"id": "nurture", "type": "notify", "channel": "email", "template": "nurture"},
    ],
    "policies": {"escalation": {"timeout_seconds": 3600}},
}


@asynccontextmanager
async def worker(client: Client, acts: OrynActivities, sticky: bool = True):
    # sticky=False mimics a crashed worker's replacement: no cached workflow state at all.
    kw = {} if sticky else {"max_cached_workflows": 0}
    async with Worker(
        client,
        task_queue=tq(),
        workflows=[OrynRunWorkflow, ConversationWorkflow, McpActionWorkflow],
        activities=acts.all(),
        **kw,
    ):
        yield


async def start(
    client: Client, tenant, definition: dict = GOLDEN, trigger: dict = LEAD
) -> tuple[WorkflowHandle, uuid.UUID]:
    rid = uuid.uuid4()
    async with owner_session() as s:
        s.add(
            Run(id=rid, tenant_id=tenant.id, temporal_workflow_id=f"wf-{rid}", started_at=datetime.now(UTC), title="t")
        )
    inp = RunInput(
        tenant_id=tenant.id, run_id=rid, definition=WorkflowDefinition.model_validate(definition), trigger=trigger
    )
    h = await client.start_workflow(OrynRunWorkflow.run, inp, id=f"wf-{rid}", task_queue=tq())
    return h, rid


async def wait_state(h: WorkflowHandle, status: str, within: float = 30) -> RunState:
    async def poll() -> RunState:
        while True:
            st = await h.query(OrynRunWorkflow.get_state)
            if st.status == status:
                return st
            await asyncio.sleep(0.1)

    return await asyncio.wait_for(poll(), within)
