"""Starting and talking to conversations. Uses Temporal update-with-start so one call either
creates the conversation workflow or reuses the running one, then returns the agent's reply."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy

from oryn.core.db import tenant_session
from oryn.models import AgentRole, Conversation, Run, RunStatus, Tenant
from oryn.orchestration.client import get_task_queue
from oryn.orchestration.conversation_workflow import AgentReply, ConversationInput, ConversationWorkflow, UserMessage

CHANNEL_TITLES = {
    "chat": "Chat with",
    "sms": "Texts with",
    "voice": "Call from",
    "email": "Email from",
    "api": "API session with",
}
DEFAULT_CHANNEL_AGENTS = {
    "chat": "support",
    "sms": "support",
    "voice": "scheduler",
    "email": "support",
    "api": "support",
}


async def get_or_create_conversation(
    tenant_id: uuid.UUID,
    channel: str,
    external_id: str,
    contact: dict[str, Any] | None = None,
    agent_role: AgentRole | None = None,
) -> tuple[Conversation, Run, AgentRole]:
    async with tenant_session(tenant_id) as s:
        tenant = await s.get(Tenant, tenant_id)
        agents = {**DEFAULT_CHANNEL_AGENTS, **((tenant.settings or {}).get("channel_agents", {}) if tenant else {})}
        role = agent_role or AgentRole(agents.get(channel, "support"))
        conv = (
            await s.execute(
                select(Conversation).where(Conversation.channel == channel, Conversation.external_id == external_id)
            )
        ).scalar_one_or_none()
        if conv is None:
            conv_id, run_id = uuid.uuid4(), uuid.uuid4()
            wf_id = f"{tenant_id}:conv:{conv_id}"
            who = (contact or {}).get("name") or (contact or {}).get("email") or external_id
            s.add(
                Run(
                    id=run_id,
                    tenant_id=tenant_id,
                    kind="conversation",
                    title=f"{CHANNEL_TITLES.get(channel, 'Conversation with')} {who}"[:300],
                    temporal_workflow_id=wf_id,
                    status=RunStatus.running,
                    started_at=datetime.now(UTC),
                )
            )
            await s.flush()
            await s.execute(
                insert(Conversation)
                .values(
                    id=conv_id,
                    tenant_id=tenant_id,
                    channel=channel,
                    external_id=external_id,
                    run_id=run_id,
                    temporal_workflow_id=wf_id,
                    status="open",
                )
                .on_conflict_do_nothing()
            )
            conv = (
                await s.execute(
                    select(Conversation).where(Conversation.channel == channel, Conversation.external_id == external_id)
                )
            ).scalar_one()
        run = await s.get(Run, conv.run_id)
        assert run
        return conv, run, role


async def send_message(
    client: Client,
    tenant_id: uuid.UUID,
    channel: str,
    external_id: str,
    msg: UserMessage,
    contact: dict[str, Any] | None = None,
    address: str | None = None,
    agent_role: AgentRole | None = None,
) -> AgentReply:
    conv, run, role = await get_or_create_conversation(tenant_id, channel, external_id, contact, agent_role)
    # Start-or-reuse, then update. (Equivalent to update-with-start, which the local test server lacks.)
    handle = await client.start_workflow(
        ConversationWorkflow.run,
        ConversationInput(
            tenant_id=tenant_id,
            conversation_id=conv.id,
            run_id=run.id,
            channel=channel,
            agent_role=role,
            contact=contact or {},
            address=address,
        ),
        id=conv.temporal_workflow_id,
        task_queue=get_task_queue(),
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
    )
    return await handle.execute_update(ConversationWorkflow.send, msg)
