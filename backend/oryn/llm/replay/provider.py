"""ReplayProvider — a deterministic, offline stand-in for an LLM.

It implements the same ``LLMProvider`` interface as Claude and drives the *same* LangGraph
loop, tool registry, approval policy and Temporal workflow. Each agent role has a small
script that reads the conversation (and the tool results so far) and picks the next tool
call, exactly as a model would. Token usage is estimated from text length and flagged
``simulated=True`` so the dashboard can label cost honestly.
"""

import hashlib
import json
import random

from pydantic import BaseModel

from oryn.llm.pricing import estimate_tokens
from oryn.llm.replay.scripts import ops, reporting, sales, scheduler, support
from oryn.llm.replay.state import ReplayMove, ReplayState
from oryn.llm.types import ChatMessage, LLMResult, ReplayContext, ToolCall, Usage
from oryn.tools.registry import ToolSpec

SCRIPTS = {
    "sales": sales.next_move,
    "scheduler": scheduler.next_move,
    "support": support.next_move,
    "reporting": reporting.next_move,
    "ops": ops.next_move,
}


class ReplayProvider:
    def __init__(self, seed: int = 7) -> None:
        self.seed = seed

    def _rng(self, ctx: ReplayContext, n: int) -> random.Random:
        h = hashlib.sha256(f"{self.seed}:{ctx.seed}:{ctx.step_key}:{n}".encode()).hexdigest()
        return random.Random(int(h[:12], 16))

    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        response_schema: type[BaseModel] | None = None,
        max_tokens: int = 4096,
        context: ReplayContext | None = None,
    ) -> LLMResult:
        ctx = context or ReplayContext(agent_role="support", step_key="default")
        state = ReplayState.build(ctx, messages, {t.name for t in tools}, self._rng(ctx, len(messages)))
        script = SCRIPTS.get(ctx.agent_role, support.next_move)
        failing = state.repeated_failure()
        mv: ReplayMove = (
            ReplayMove("control.escalate_to_human", {"reason": f"{failing} kept failing; needs a human"})
            if failing
            else script(state)
        )
        call = ToolCall(id=f"replay_{len(messages)}", name=mv.tool, arguments=mv.args)
        prompt = system + "".join(m.content + json.dumps([c.arguments for c in m.tool_calls]) for m in messages)
        usage = Usage(
            input_tokens=estimate_tokens(prompt) + 40 * len(tools),
            output_tokens=estimate_tokens(json.dumps(mv.args)) + 25,
        )
        return LLMResult(text="", tool_calls=[call], usage=usage, model=model, simulated=True, stop_reason="tool_use")
