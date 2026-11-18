"""Span recorder: every agent decision, LLM call and tool call becomes a row in ``spans`` and a
live event. Each write uses its own short transaction so traces survive even when the
surrounding agent step rolls back and is retried."""

import uuid
from decimal import Decimal
from typing import Any

from oryn.core.db import tenant_session
from oryn.llm.types import Usage
from oryn.models import Span, SpanKind
from oryn.observability.bus import EventBus, LiveEvent
from oryn.observability.clock import OffsetClock


def _safe(d: dict[str, Any] | None) -> dict[str, Any] | None:
    import json

    return None if d is None else json.loads(json.dumps(d, default=str))


class DbSpanSink:
    def __init__(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID, bus: EventBus, clock: OffsetClock, attempt: int = 1
    ) -> None:
        self.tenant_id, self.run_id, self.bus, self.clock, self.attempt = tenant_id, run_id, bus, clock, attempt

    async def start(
        self,
        kind: SpanKind,
        name: str,
        input: dict[str, Any] | None = None,
        parent_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        span = Span(
            id=uuid.uuid4(),
            tenant_id=self.tenant_id,
            run_id=self.run_id,
            parent_span_id=parent_id,
            agent_id=agent_id,
            kind=kind,
            name=name[:200],
            status="running",
            input=_safe(input),
            started_at=self.clock.now(),
            attempt=self.attempt,
        )
        async with tenant_session(self.tenant_id) as s:
            s.add(span)
        await self.bus.publish(
            LiveEvent(
                type="span.started",
                tenant_id=self.tenant_id,
                run_id=self.run_id,
                data={
                    "span_id": str(span.id),
                    "kind": kind.value,
                    "name": span.name,
                    "parent_span_id": str(parent_id) if parent_id else None,
                },
            )
        )
        return span.id

    async def end(
        self,
        span_id: uuid.UUID,
        output: dict[str, Any] | None = None,
        status: str = "ok",
        usage: Usage | None = None,
        cost: Decimal | None = None,
        simulated: bool = False,
    ) -> None:
        async with tenant_session(self.tenant_id) as s:
            span = await s.get(Span, span_id)
            if span is None:
                return
            span.output, span.status, span.ended_at = _safe(output), status, self.clock.now()
            span.simulated = simulated
            if usage:
                span.input_tokens, span.output_tokens = usage.input_tokens, usage.output_tokens
            if cost is not None:
                span.cost_usd = cost
        await self.bus.publish(
            LiveEvent(
                type="span.ended",
                tenant_id=self.tenant_id,
                run_id=self.run_id,
                data={"span_id": str(span_id), "status": status},
            )
        )

    async def event(
        self,
        kind: SpanKind,
        name: str,
        data: dict[str, Any] | None = None,
        status: str = "ok",
        parent_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """A zero-duration span (e.g. a retry, a handoff, an approval decision)."""
        sid = await self.start(kind, name, data, parent_id)
        await self.end(sid, data, status=status)
        return sid
