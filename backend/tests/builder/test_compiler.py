import pytest

from oryn.builder.grammar import compile_offline
from oryn.workflows.dsl import validate_definition
from tests.builder.goldens import GOLDENS


@pytest.mark.parametrize(("text", "expected"), GOLDENS, ids=[g[1]["name"] for g in GOLDENS])
def test_golden(text: str, expected: dict) -> None:
    r = compile_offline(text)
    assert r.errors == [] and r.warnings == []
    assert r.definition is not None
    assert r.definition.model_dump(mode="json", by_alias=True) == expected
    assert validate_definition(r.definition) == []


def test_unknown_phrase_becomes_warning() -> None:
    r = compile_offline("When a new lead arrives, have the sales agent qualify it. Do a backflip.")
    assert r.definition is not None and len(r.definition.steps) == 1
    assert r.warnings == ["Didn't understand: 'Do a backflip' — it was not added."]
    assert [c.rule for c in r.clauses] == ["trigger", "agent", None]


def test_empty_text_returns_error() -> None:
    r = compile_offline("   ")
    assert r.definition is None and r.errors


def test_missing_trigger_error() -> None:
    r = compile_offline("Have the sales agent qualify the lead.")
    assert r.definition is None
    assert r.errors == ["Missing trigger — start with 'When …' (e.g. 'When a new lead arrives') or 'Every …'."]


def test_trigger_without_steps_is_error() -> None:
    r = compile_offline("When a new lead arrives.")
    assert r.definition is None and "no steps" in r.errors[0]


def test_approval_gate_and_vip_condition() -> None:
    r = compile_offline(
        "When a new lead arrives, get an admin's approval. If the customer is a VIP, have the "
        "sales agent call them personally."
    )
    steps = r.definition.model_dump(mode="json", by_alias=True)["steps"]
    assert steps[0] == {
        "id": "approval",
        "next": None,
        "type": "approval",
        "description": "Admin approval",
        "min_role": "admin",
    }
    assert steps[1]["if"] == "blackboard.vip == true" and steps[1]["else"] == "end"


def test_amount_condition() -> None:
    r = compile_offline(
        "When a new lead arrives, if the budget is over $5,000, have the sales agent escalate "
        "it to the owner, otherwise have the sales agent qualify it."
    )
    cond = r.definition.model_dump(mode="json", by_alias=True)["steps"][0]
    assert cond["if"] == "trigger.budget_usd > 5000"


class _JsonLLM:
    def __init__(self, text: str) -> None:
        self.text = text

    async def complete(self, **kw):
        from oryn.llm.types import LLMResult, Usage

        assert kw["response_schema"] is not None
        return LLMResult(
            text=self.text, tool_calls=[], usage=Usage(), model="m", simulated=False, stop_reason="end_turn"
        )


async def test_llm_draft_is_validated() -> None:
    import json

    from oryn.builder.drafts import draft_workflow
    from tests.builder.goldens import GOLDENS

    r = await draft_workflow("anything", _JsonLLM(json.dumps(GOLDENS[1][1])))
    assert r.errors == [] and r.definition.trigger.event == "ticket.created"


async def test_llm_failure_falls_back_to_offline() -> None:
    from oryn.builder.drafts import draft_workflow
    from tests.builder.goldens import GOLDENS

    r = await draft_workflow(GOLDENS[0][0], _JsonLLM("not json"))
    assert r.definition is not None and r.definition.trigger.event == "lead.created"
    assert any("offline" in w for w in r.warnings)


def test_ui_examples_compile_cleanly() -> None:
    from oryn.builder.examples import EXAMPLES

    for ex in EXAMPLES:
        r = compile_offline(ex)
        assert r.definition is not None and r.errors == [] and r.warnings == [], ex
