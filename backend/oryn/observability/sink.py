import uuid
from decimal import Decimal
from typing import Any, Protocol

from oryn.llm.types import Usage
from oryn.models import SpanKind


class SpanSink(Protocol):
    async def start(
        self,
        kind: SpanKind,
        name: str,
        input: dict[str, Any] | None = None,
        parent_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
    ) -> uuid.UUID: ...

    async def end(
        self,
        span_id: uuid.UUID,
        output: dict[str, Any] | None = None,
        status: str = "ok",
        usage: Usage | None = None,
        cost: Decimal | None = None,
        simulated: bool = False,
    ) -> None: ...
