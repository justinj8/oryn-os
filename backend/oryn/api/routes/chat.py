"""Public chat API (the website widget and the dashboard's chat simulator)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from temporalio.client import Client, WorkflowUpdateFailedError
from temporalio.service import RPCError

from oryn.api.routes.webhooks import tenant_by_slug
from oryn.core.db import tenant_session
from oryn.models import Conversation, SbMessage
from oryn.observability.bus import get_event_bus
from oryn.orchestration.client import temporal_client
from oryn.orchestration.conversation_workflow import AgentReply, UserMessage
from oryn.services.conversations import send_message

router = APIRouter(prefix="/api/chat", tags=["chat"])
RATE_LIMIT_PER_MIN = 30


class SessionIn(BaseModel):
    name: str | None = None
    email: str | None = None


class MessageIn(BaseModel):
    text: str = Field(max_length=4000)
    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex, max_length=100)

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message text is empty")
        return v.strip()


class TranscriptItem(BaseModel):
    direction: str
    body: str
    sent_at: datetime


async def rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"oryn:ratelimit:chat:{ip}:{datetime.now(UTC).strftime('%Y%m%d%H%M')}"
    redis = get_event_bus().redis
    try:
        n = await redis.incr(key)
        if n == 1:
            await redis.expire(key, 70)
    except Exception:
        return  # fail open: rate limiting must not take the chat down
    if n > RATE_LIMIT_PER_MIN:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "slow down")


@router.post("/{tenant_slug}/sessions", dependencies=[Depends(rate_limit)])
async def new_session(tenant_slug: str, body: SessionIn) -> dict[str, str]:
    await tenant_by_slug(tenant_slug)
    return {"session_id": uuid.uuid4().hex}


@router.post(
    "/{tenant_slug}/sessions/{session_id}/messages", response_model=AgentReply, dependencies=[Depends(rate_limit)]
)
async def post_message(
    tenant_slug: str, session_id: str, body: MessageIn, client: Client = Depends(temporal_client)
) -> AgentReply:
    tenant = await tenant_by_slug(tenant_slug)
    try:
        return await send_message(
            client, tenant.id, "chat", session_id, UserMessage(text=body.text, message_id=body.message_id)
        )
    except (WorkflowUpdateFailedError, RPCError) as e:
        raise HTTPException(status.HTTP_409_CONFLICT, f"conversation unavailable: {e}") from e


@router.get("/{tenant_slug}/sessions/{session_id}/messages", response_model=list[TranscriptItem])
async def transcript(tenant_slug: str, session_id: str) -> list[TranscriptItem]:
    tenant = await tenant_by_slug(tenant_slug)
    async with tenant_session(tenant.id) as s:
        conv = (
            await s.execute(
                select(Conversation).where(Conversation.channel == "chat", Conversation.external_id == session_id)
            )
        ).scalar_one_or_none()
        if conv is None:
            return []
        rows = (
            await s.execute(select(SbMessage).where(SbMessage.conversation_id == conv.id).order_by(SbMessage.sent_at))
        ).scalars()
        return [TranscriptItem(direction=m.direction, body=m.body, sent_at=m.sent_at) for m in rows]
