import json

import anthropic
import httpx2 as httpx
import pytest

from oryn.connectors.errors import ErrorClass, classify_error
from oryn.llm.anthropic_provider import AnthropicProvider
from oryn.llm.types import ChatMessage, ToolCall
from oryn.tools.registry import default_registry


def _client(handler) -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(
        api_key="test", max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


def _message(content: list[dict], stop: str = "tool_use") -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": {"input_tokens": 120, "output_tokens": 30},
    }


async def test_anthropic_maps_tool_use_and_history() -> None:
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        return httpx.Response(
            200,
            json=_message(
                [{"type": "tool_use", "id": "tu_2", "name": "calendar__find_slots", "input": {"duration_min": 30}}]
            ),
        )

    p = AnthropicProvider(_client(handler))
    specs = default_registry().specs_for(["calendar.*"])
    history = [
        ChatMessage(role="user", content="Book me in"),
        ChatMessage(role="assistant", tool_calls=[ToolCall(id="tu_1", name="crm.find_contact", arguments={})]),
        ChatMessage(role="tool", tool_call_id="tu_1", content='{"found": false}'),
    ]
    r = await p.complete(model="claude-opus-5-5", system="You schedule.", messages=history, tools=specs)
    assert r.tool_calls[0].name == "calendar.find_slots"
    assert r.tool_calls[0].arguments == {"duration_min": 30}
    assert (r.usage.input_tokens, r.usage.output_tokens) == (120, 30)
    assert r.simulated is False and r.stop_reason == "tool_use"
    # wire format: dotted names encoded, tool results grouped into a user turn
    assert {t["name"] for t in seen["tools"]} >= {"calendar__find_slots", "control__finish"}
    assert seen["messages"][1]["content"][0]["name"] == "crm__find_contact"
    assert seen["messages"][2]["content"][0]["type"] == "tool_result"
    assert seen["fallbacks"] == "default"


async def test_anthropic_replays_raw_assistant_blocks() -> None:
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        return httpx.Response(200, json=_message([{"type": "text", "text": "done"}], stop="end_turn"))

    raw = [{"type": "thinking", "thinking": "", "signature": "sig"}, {"type": "text", "text": "hi"}]
    p = AnthropicProvider(_client(handler))
    r = await p.complete(
        model="claude-opus-5-5",
        system="s",
        messages=[
            ChatMessage(role="user", content="a"),
            ChatMessage(role="assistant", content="hi", raw=raw),
            ChatMessage(role="user", content="b"),
        ],
        tools=[],
    )
    assert seen["messages"][1]["content"] == raw
    assert r.text == "done" and r.raw is not None


async def test_anthropic_429_raises_rate_limited() -> None:
    p = AnthropicProvider(
        _client(
            lambda req: httpx.Response(
                429, json={"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}
            )
        )
    )
    with pytest.raises(Exception) as ei:
        await p.complete(
            model="claude-opus-5-5", system="s", messages=[ChatMessage(role="user", content="x")], tools=[]
        )
    assert classify_error(ei.value) is ErrorClass.rate_limited
