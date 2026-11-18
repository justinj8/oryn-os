from oryn.core.tenancy import Role
from oryn.policies.escalation import EscalationPolicy, next_escalation

POL = EscalationPolicy(timeout_seconds=3600)


def test_operator_escalates_to_admin() -> None:
    d = next_escalation(Role.operator, 0, POL)
    assert (d.action, d.next_role, d.timeout_seconds) == ("escalate", Role.admin, 3600)


def test_admin_escalates_to_owner_with_doubled_timeout() -> None:
    d = next_escalation(Role.admin, 1, POL)
    assert (d.action, d.next_role, d.timeout_seconds) == ("escalate", Role.owner, 7200)


def test_top_of_ladder_auto_rejects() -> None:
    d = next_escalation(Role.owner, 2, POL)
    assert d.action == "auto_reject" and d.next_role is None and d.timeout_seconds is None
    assert d.reason == "no decision after 2 escalations"


def test_role_above_ladder_start_skips_lower_rungs() -> None:
    # An approval that already required admin escalates straight to owner.
    d = next_escalation(Role.admin, 0, POL)
    assert d.next_role is Role.owner


def test_custom_ladder() -> None:
    d = next_escalation(Role.operator, 0, EscalationPolicy(ladder=(Role.operator, Role.owner)))
    assert d.next_role is Role.owner
