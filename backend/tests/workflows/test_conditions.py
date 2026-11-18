import pytest

from oryn.workflows.conditions import ConditionSyntaxError, evaluate, parse


@pytest.mark.parametrize(
    ("expr", "scope", "expected"),
    [
        ("blackboard.qualified == true", {"blackboard": {"qualified": True}}, True),
        ("blackboard.qualified == true", {"blackboard": {"qualified": False}}, False),
        ("blackboard.qualified", {"blackboard": {"qualified": 1}}, True),
        (
            "trigger.amount > 5000 and blackboard.vip == true",
            {"trigger": {"amount": 6000}, "blackboard": {"vip": True}},
            True,
        ),
        ("trigger.amount > 5000 and blackboard.vip == true", {"trigger": {"amount": 6000}, "blackboard": {}}, False),
        ("trigger.amount <= 100 or trigger.source == 'phone'", {"trigger": {"amount": 500, "source": "phone"}}, True),
        ('trigger.source != "web"', {"trigger": {"source": "web"}}, False),
        ("blackboard.missing.deep == 3", {"blackboard": {}}, False),
        ("blackboard.x == null", {"blackboard": {}}, True),
        ("trigger.amount >= 10.5", {"trigger": {"amount": "11"}}, True),
    ],
)
def test_evaluate(expr: str, scope: dict, expected: bool) -> None:
    assert evaluate(expr, scope) is expected


@pytest.mark.parametrize("bad", ["__import__('os')", "blackboard.x ===", "", "a == ", "1 == 1 and", "x.y(1)"])
def test_syntax_errors(bad: str) -> None:
    with pytest.raises(ConditionSyntaxError):
        parse(bad)
