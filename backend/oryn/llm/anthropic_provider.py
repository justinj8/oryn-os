"""Claude via the official Anthropic SDK.

Notes on the request shape (Claude Opus 5.5 era):
* thinking is adaptive by default and cannot be disabled, so we omit ``thinking`` and set
  ``output_config.effort`` explicitly (the model default is ``medium``);
* forced ``tool_choice`` is rejected, so structured output uses ``output_config.format``;
* server-side refusal fallbacks are enabled (``fallbacks: "default"``);
* assistant content blocks are replayed unchanged (``ChatMessage.raw``) so thinking blocks
  stay valid across turns.
"""

import json
from typing import Any

import anthropic
from pydantic import BaseModel

from oryn.connectors.errors import ConnectorError
from oryn.llm.types import ChatMessage, LLMResult, ReplayContext, ToolCall, Usage
from oryn.tools.registry import ToolSpec, default_registry, from_wire, to_wire

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Structured outputs need additionalProperties=false and all properties required."""

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            node = {k: walk(v) for k, v in node.items()}
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            return node
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


class AnthropicProvider:
    def __init__(self, client: anthropic.AsyncAnthropic, effort: str = "medium") -> None:
        self.client = client
        self.effort = effort

    @staticmethod
    def _to_wire_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "user":
                out.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                if m.raw is not None:
                    content: list[dict[str, Any]] = m.raw
                else:
                    content = [{"type": "text", "text": m.content}] if m.content else []
                    content += [
                        {"type": "tool_use", "id": c.id, "name": to_wire(c.name), "input": c.arguments}
                        for c in m.tool_calls
                    ]
                out.append({"role": "assistant", "content": content})
            else:  # tool results: consecutive ones share one user turn
                block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
        return out

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
        reg = default_registry()
        output_config: dict[str, Any] = {"effort": self.effort}
        if response_schema is not None:
            output_config["format"] = {
                "type": "json_schema",
                "schema": _strict_schema(response_schema.model_json_schema()),
            }
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": self._to_wire_messages(messages),
            "output_config": output_config,
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",
        }
        if tools:
            kwargs["tools"] = [reg.json_schema(t) for t in tools]
        try:
            resp = await self.client.beta.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            raise ConnectorError(str(e.message), provider="anthropic", status_code=e.status_code) from e
        except anthropic.APIConnectionError as e:
            raise ConnectionError(f"anthropic: {e}") from e

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        raw: list[dict[str, Any]] = []
        for block in resp.content:
            raw.append(block.model_dump(mode="json", exclude_none=True))
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                args = block.input if isinstance(block.input, dict) else json.loads(str(block.input))
                calls.append(ToolCall(id=block.id, name=from_wire(block.name), arguments=args))
        return LLMResult(
            text="".join(text_parts),
            tool_calls=calls,
            usage=Usage(input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens),
            model=resp.model,
            simulated=False,
            stop_reason=resp.stop_reason or "end_turn",
            raw=raw,
        )
