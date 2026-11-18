import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from oryn.core.db import tenant_session
from oryn.core.security import AuthError, decode_access_token
from oryn.models import Membership
from oryn.observability.bus import EventBus, get_event_bus

router = APIRouter(prefix="/api", tags=["events"])


async def stream_events(bus: EventBus, tenant_id: uuid.UUID, request: Any) -> AsyncIterator[dict[str, str]]:
    async for ev in bus.subscribe(tenant_id):
        if await request.is_disconnected():
            break
        yield {"event": ev.type, "data": json.dumps(ev.model_dump(mode="json"))}


@router.get("/events/stream")
async def events_stream(request: Request, tenant_id: uuid.UUID, token: str) -> EventSourceResponse:
    """Server-sent events for one tenant. ``EventSource`` can't send headers, so the JWT comes
    as a query parameter; membership is checked exactly like ``X-Tenant-Id``."""
    try:
        user_id = decode_access_token(token)
    except AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from e
    async with tenant_session(tenant_id) as s:
        member = (await s.execute(select(Membership.id).where(Membership.user_id == user_id))).first()
    if not member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a member of this tenant")
    return EventSourceResponse(stream_events(get_event_bus(), tenant_id, request), ping=15)
