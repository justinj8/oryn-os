"""USD per million tokens (input, output). Source: Anthropic pricing, Nov 2026."""

import math
from decimal import Decimal

from oryn.llm.types import Usage

PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "claude-fable-5-2": (Decimal("8"), Decimal("40")),
    "claude-opus-5-5": (Decimal("4"), Decimal("20")),
    "claude-opus-5": (Decimal("5"), Decimal("25")),
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10")),
    "claude-sonnet-5": (Decimal("2"), Decimal("10")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
}
DEFAULT_MODEL_PRICE = "claude-opus-5-5"
_MTOK = Decimal(1_000_000)


def cost_usd(model: str, usage: Usage) -> Decimal:
    p_in, p_out = PRICES.get(model, PRICES[DEFAULT_MODEL_PRICE])
    return (Decimal(usage.input_tokens) * p_in + Decimal(usage.output_tokens) * p_out) / _MTOK


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)
