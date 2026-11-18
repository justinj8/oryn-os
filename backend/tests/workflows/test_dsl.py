from oryn.workflows.dsl import WorkflowDefinition, validate_definition

SPEC_EXAMPLE = {
    "name": "Inbound lead to booked meeting",
    "trigger": {"event": "lead.created"},
    "steps": [
        {"id": "qualify", "type": "agent", "role": "sales", "goal": "Qualify the lead and propose a quote"},
        {"id": "gate", "type": "condition", "if": "blackboard.qualified == true", "then": "book", "else": "nurture"},
        {
            "id": "book",
            "type": "agent",
            "role": "scheduler",
            "goal": "Book a 30-min consult within 5 business days",
            "next": "end",
        },
        {"id": "nurture", "type": "notify", "channel": "email", "template": "nurture"},
    ],
    "policies": {"approval": {"discount_pct_over": 10, "refund_usd_over": 200}},
}


def test_spec_example_parses_and_validates() -> None:
    d = WorkflowDefinition.model_validate(SPEC_EXAMPLE)
    assert validate_definition(d) == []
    assert d.policies.approval.discount_pct_over == 10
    assert d.step("gate").then == "book"
    assert d.next_of("qualify") == "gate" and d.next_of("book") == "end" and d.next_of("nurture") == "end"


def _with(steps) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate({"name": "x", "trigger": {"event": "e"}, "steps": steps})


def test_unknown_next_reference_error() -> None:
    errs = validate_definition(_with([{"id": "a", "type": "wait", "seconds": 5, "next": "zzz"}]))
    assert errs == ["step 'a' points to unknown step 'zzz'"]


def test_cycle_detected() -> None:
    d = _with(
        [{"id": "a", "type": "wait", "seconds": 1, "next": "b"}, {"id": "b", "type": "wait", "seconds": 1, "next": "a"}]
    )
    assert any("cycle" in e for e in validate_definition(d))


def test_duplicate_ids() -> None:
    d = _with([{"id": "a", "type": "wait", "seconds": 1}, {"id": "a", "type": "wait", "seconds": 2}])
    assert "duplicate step id 'a'" in validate_definition(d)


def test_empty_steps() -> None:
    assert "workflow has no steps" in validate_definition(_with([]))


def test_bad_condition_reported() -> None:
    d = _with([{"id": "c", "type": "condition", "if": "blackboard.x ===", "then": "end", "else": "end"}])
    assert any(e.startswith("step 'c' has an invalid condition") for e in validate_definition(d))


def test_roundtrip_json() -> None:
    d = WorkflowDefinition.model_validate(SPEC_EXAMPLE)
    again = WorkflowDefinition.model_validate(d.model_dump(mode="json", by_alias=True))
    assert again == d
