import json
import random
from dataclasses import dataclass, field
from typing import Any

from oryn.llm.types import ChatMessage, ReplayContext, ToolCall


@dataclass
class Call:
    call: ToolCall
    result: dict[str, Any] | None

    @property
    def name(self) -> str:
        return self.call.name

    @property
    def ok(self) -> bool:
        return self.result is not None and "error" not in self.result


@dataclass
class ReplayMove:
    tool: str
    args: dict[str, Any]


@dataclass
class ReplayState:
    ctx: ReplayContext
    messages: list[ChatMessage]
    tools: set[str]
    rng: random.Random
    calls: list[Call] = field(default_factory=list)  # all calls in the thread
    turn_calls: list[Call] = field(default_factory=list)  # calls since the latest user message

    @classmethod
    def build(cls, ctx: ReplayContext, messages: list[ChatMessage], tools: set[str], rng: random.Random):
        results: dict[str, dict[str, Any]] = {}
        for m in messages:
            if m.role == "tool" and m.tool_call_id:
                try:
                    results[m.tool_call_id] = json.loads(m.content or "{}")
                except json.JSONDecodeError:
                    results[m.tool_call_id] = {"text": m.content}
        st = cls(ctx=ctx, messages=messages, tools=tools, rng=rng)
        for m in messages:
            if m.role == "user":
                st.turn_calls = []
            for c in m.tool_calls if m.role == "assistant" else []:
                call = Call(c, results.get(c.id))
                st.calls.append(call)
                st.turn_calls.append(call)
        return st

    # --- helpers for scripts
    @property
    def trigger(self) -> dict[str, Any]:
        return self.ctx.trigger

    @property
    def bb(self) -> dict[str, Any]:
        return self.ctx.blackboard

    def last(self, tool: str, turn_only: bool = True) -> Call | None:
        for c in reversed(self.turn_calls if turn_only else self.calls):
            if c.name == tool:
                return c
        return None

    def done(self, tool: str, turn_only: bool = True) -> bool:
        return self.last(tool, turn_only) is not None

    def user_texts(self) -> list[str]:
        return [m.content for m in self.messages if m.role == "user"]

    def last_user(self) -> str:
        texts = self.user_texts()
        return texts[-1] if texts else ""

    def prompt_text(self) -> str:
        return "\n".join(self.user_texts())

    def repeated_failure(self) -> str | None:
        """A tool that has failed twice in this turn → the agent should stop and escalate."""
        failures: dict[str, int] = {}
        for c in self.turn_calls:
            if c.result is not None and "error" in c.result:
                failures[c.name] = failures.get(c.name, 0) + 1
                if failures[c.name] >= 2:
                    return c.name
        return None

    def failed_last(self) -> Call | None:
        if self.turn_calls and self.turn_calls[-1].result and "error" in self.turn_calls[-1].result:
            return self.turn_calls[-1]
        return None

    def pick(self, options: list[str]) -> str:
        return options[self.rng.randrange(len(options))]


def move(tool: str, **args: Any) -> ReplayMove:
    return ReplayMove(tool, args)
