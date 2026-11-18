from decimal import Decimal

from oryn.core.config import Settings
from oryn.llm.factory import get_llm_provider
from oryn.llm.pricing import cost_usd, estimate_tokens
from oryn.llm.types import Usage


def test_cost_opus() -> None:
    assert cost_usd("claude-opus-5-5", Usage(input_tokens=1_000_000, output_tokens=1_000_000)) == Decimal("24")


def test_cost_unknown_model_uses_default_price() -> None:
    u = Usage(input_tokens=1000, output_tokens=0)
    assert cost_usd("something-new", u) == cost_usd("claude-opus-5-5", u)


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd" * 10) == 10


def test_factory_defaults_to_replay() -> None:
    from oryn.llm.replay.provider import ReplayProvider

    assert isinstance(get_llm_provider(Settings()), ReplayProvider)


def test_factory_needs_key_for_anthropic() -> None:
    p = get_llm_provider(Settings(llm_provider="anthropic", anthropic_api_key=None))
    assert type(p).__name__ != "AnthropicProvider"
