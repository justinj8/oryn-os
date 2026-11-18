"""What happens when nobody answers an approval request.

``next_escalation`` is pure and deterministic on purpose: it is called from *inside Temporal
workflow code*, which must replay identically after a crash. It can't read the clock, the
database or random state — so the workflow passes in everything it needs.

Behaviour: walk up a role ladder (operator → admin → owner), doubling the wait at each rung
so senior people are interrupted less often, and auto-reject once the ladder is exhausted.
Rejecting (rather than auto-approving) is the safe default: a stalled approval means the
agent continues *without* the risky action, and the decision is recorded with its reason.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from oryn.core.tenancy import Role


class EscalationPolicy(BaseModel):
    timeout_seconds: int = 3600
    ladder: tuple[Role, ...] = (Role.operator, Role.admin, Role.owner)


@dataclass(frozen=True)
class EscalationDecision:
    action: Literal["escalate", "auto_reject"]
    next_role: Role | None
    timeout_seconds: int | None
    reason: str


def next_escalation(current_role: Role, level: int, policy: EscalationPolicy) -> EscalationDecision:
    higher = [r for r in policy.ladder if r.rank > current_role.rank]
    if not higher:
        return EscalationDecision("auto_reject", None, None, f"no decision after {level} escalations")
    nxt = min(higher, key=lambda r: r.rank)
    return EscalationDecision(
        "escalate",
        nxt,
        policy.timeout_seconds * 2**level,
        f"no decision from {current_role.value} within the time limit; escalated to {nxt.value}",
    )
