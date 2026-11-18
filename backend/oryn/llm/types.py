from typing import Any, Literal, Protocol

from pydantic import BaseModel

from oryn.tools.registry import ToolSpec


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = []
    tool_call_id: str | None = None
    # Provider-native assistant content blocks (e.g. thinking blocks) that must be replayed unchanged.
    raw: list[dict[str, Any]] | None = None


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class LLMResult(BaseModel):
    text: str
    tool_calls: list[ToolCall]
    usage: Usage
    model: str
    simulated: bool
    stop_reason: str
    raw: list[dict[str, Any]] | None = None


class ReplayContext(BaseModel):
    """Extra context the offline Replay model uses; real providers ignore it."""

    agent_role: str
    step_key: str
    seed: int = 7
    blackboard: dict[str, Any] = {}
    trigger: dict[str, Any] = {}


class LLMProvider(Protocol):
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
    ) -> LLMResult: ...
