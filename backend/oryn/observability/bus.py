"""Live events over Redis pub/sub, one channel per tenant."""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, Field
from redis.asyncio import Redis

from oryn.core.config import get_settings

EventType = Literal[
    "run.started",
    "run.updated",
    "span.started",
    "span.ended",
    "approval.requested",
    "approval.decided",
    "message.sent",
    "event.received",
]


class LiveEvent(BaseModel):
    type: EventType
    tenant_id: uuid.UUID
    run_id: uuid.UUID | None = None
    data: dict[str, Any] = {}
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))


def channel(tenant_id: uuid.UUID) -> str:
    return f"oryn:{tenant_id}:events"


class EventBus:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def publish(self, event: LiveEvent) -> None:
        try:
            await self.redis.publish(channel(event.tenant_id), event.model_dump_json())
        except Exception:  # live updates are best-effort; never fail business work on them
            from oryn.core.logging import log

            log.warning("bus.publish_failed", type=event.type)

    async def subscribe(self, tenant_id: uuid.UUID) -> AsyncIterator[LiveEvent]:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel(tenant_id))
        try:
            async for msg in pubsub.listen():
                if msg.get("type") == "message":
                    yield LiveEvent.model_validate(json.loads(msg["data"]))
        finally:
            await pubsub.unsubscribe(channel(tenant_id))
            await pubsub.aclose()


@lru_cache
def get_event_bus() -> EventBus:
    return EventBus(Redis.from_url(get_settings().redis_url, decode_responses=True))
