"""Public, API-key authenticated agent API: talk to any agent from your own systems."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from temporalio.client import Client

from oryn.api.deps import TenantContext, tenant_ctx
from oryn.api.routes.runs import RunOut
from oryn.core.db import tenant_session
from oryn.models import Agent, Run
from oryn.orchestration.client import temporal_client
from oryn.orchestration.conversation_workflow import AgentReply, UserMessage
from oryn.services.conversations import send_message

router = APIRouter(prefix="/v1", tags=["public api"])


class InvokeIn(BaseModel):
    input: str = Field(min_length=1, max_length=8000)
    session_id: str | None = Field(None, max_length=100)
    message_id: str | None = Field(None, max_length=100)


class InvokeOut(AgentReply):
    session_id: str


@router.post("/agents/{agent_id}/invoke", response_model=InvokeOut)
async def invoke(
    agent_id: uuid.UUID,
    body: InvokeIn,
    ctx: TenantContext = Depends(tenant_ctx),
    client: Client = Depends(temporal_client),
) -> InvokeOut:
    async with tenant_session(ctx.tenant_id) as s:
        agent = (
            await s.execute(select(Agent).where(Agent.id == agent_id, Agent.enabled.is_(True)))
        ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    session_id = body.session_id or uuid.uuid4().hex
    reply = await send_message(
        client,
        ctx.tenant_id,
        "api",
        f"{agent_id}:{session_id}",
        UserMessage(text=body.input, message_id=body.message_id or uuid.uuid4().hex),
        agent_role=agent.role,
    )
    return InvokeOut(**reply.model_dump(), session_id=session_id)


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: uuid.UUID, ctx: TenantContext = Depends(tenant_ctx)) -> RunOut:
    async with tenant_session(ctx.tenant_id) as s:
        run = await s.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return RunOut.of(run)
