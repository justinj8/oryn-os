"""In-memory fakes for tests."""

import uuid
from decimal import Decimal
from typing import Any


class FakeSpanSink:
    def __init__(self) -> None:
        self.spans: dict[uuid.UUID, dict[str, Any]] = {}

    async def start(self, kind, name, input=None, parent_id=None, agent_id=None) -> uuid.UUID:
        sid = uuid.uuid4()
        self.spans[sid] = {"kind": str(kind), "name": name, "input": input, "parent": parent_id, "open": True}
        return sid

    async def end(self, span_id, output=None, status="ok", usage=None, cost=None, simulated=False) -> None:
        self.spans[span_id].update(open=False, output=output, status=status, cost=cost or Decimal(0))

    def kinds(self) -> list[str]:
        return [s["kind"] for s in self.spans.values()]
