import pytest

from oryn.core.tenancy import Role
from oryn.models import Autonomy
from oryn.policies.approval import ProposedAction, WorkflowPolicies, evaluate_approval
from oryn.tools.registry import default_registry

POL = WorkflowPolicies()


def act(tool: str, **args) -> ProposedAction:
    return ProposedAction.from_spec(default_registry().get(tool).spec, args)


def test_read_only_never_needs_approval_even_under_suggest() -> None:
    r = evaluate_approval(act("calendar.find_slots"), Autonomy.suggest, POL)
    assert not r.required and r.min_role is None and r.reasons == ()


def test_suggest_autonomy_gates_every_side_effect() -> None:
    r = evaluate_approval(act("crm.add_note", contact_id="x", text="hi"), Autonomy.suggest, POL)
    assert r.required and r.min_role is Role.operator
    assert "agent autonomy is 'suggest'" in r.reasons


@pytest.mark.parametrize(("autonomy", "required"), [(Autonomy.autonomous, False), (Autonomy.act_with_approval, True)])
def test_medium_risk_depends_on_autonomy(autonomy: Autonomy, required: bool) -> None:
    r = evaluate_approval(act("crm.add_note", contact_id="x", text="hi"), autonomy, POL)
    assert r.required is required
    assert r.min_role is (Role.operator if required else None)


def test_small_discount_still_gated_as_high_risk() -> None:
    r = evaluate_approval(act("crm.apply_discount", deal_id="d", discount_pct=8), Autonomy.autonomous, POL)
    assert r.required and r.min_role is Role.operator
    assert r.reasons == ("crm.apply_discount is a high-risk action",)


def test_discount_over_policy_adds_reason() -> None:
    r = evaluate_approval(act("crm.apply_discount", deal_id="d", discount_pct=15), Autonomy.autonomous, POL)
    assert "discount 15% exceeds 10% policy" in r.reasons
    assert r.min_role is Role.operator


@pytest.mark.parametrize(
    ("amount", "role"),
    [(150, Role.operator), (350, Role.operator), (750, Role.admin), (6000, Role.owner)],
)
def test_refund_thresholds(amount: float, role: Role) -> None:
    r = evaluate_approval(act("billing.issue_refund", invoice_id="i", amount_usd=amount), Autonomy.autonomous, POL)
    assert r.required and r.min_role is role


def test_large_refund_accumulates_reasons() -> None:
    r = evaluate_approval(act("billing.issue_refund", invoice_id="i", amount_usd=6000), Autonomy.autonomous, POL)
    assert len(r.reasons) >= 3
    assert "amount $6,000 exceeds $5,000 owner threshold" in r.reasons


def test_policies_are_configurable() -> None:
    strict = WorkflowPolicies(discount_pct_over=5)
    r = evaluate_approval(act("crm.apply_discount", deal_id="d", discount_pct=8), Autonomy.autonomous, strict)
    assert "discount 8% exceeds 5% policy" in r.reasons
