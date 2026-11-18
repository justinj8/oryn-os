"""Approval policy: which agent actions need a human, and how senior that human must be.

``evaluate_approval`` is a pure function of (action, agent autonomy, workflow policy). It has
no I/O, so it is trivially testable, and it is evaluated *inside the agent loop* at the
moment an agent proposes an action — before anything touches the outside world.

Design choices worth defending:
* Rules accumulate. Every rule that fires adds a reason and the strictest role wins, so a
  reviewer sees *all* the reasons an action was held, not just the first.
* Risk comes from the tool's spec (owned by the platform), thresholds come from the
  workflow (owned by the business), autonomy comes from the agent (owned by its admin).
  Three owners, one decision.
* Money thresholds read the amount from the field the tool spec declares
  (``amount_field`` / ``percent_field``), so adding a new money-moving tool doesn't mean
  editing this function.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from oryn.core.tenancy import Role
from oryn.models import Autonomy
from oryn.tools.registry import RiskLevel, ToolSpec


class WorkflowPolicies(BaseModel):
    discount_pct_over: float = 10
    refund_usd_over: float = 200
    admin_refund_usd_over: float = 500
    owner_amount_usd_over: float = 5000


@dataclass(frozen=True)
class ProposedAction:
    tool: str
    args: dict[str, Any]
    risk: RiskLevel
    side_effect: bool
    amount_usd: float | None = None
    percent: float | None = None

    @classmethod
    def from_spec(cls, spec: ToolSpec, args: dict[str, Any]) -> "ProposedAction":
        def num(field: str | None) -> float | None:
            if field is None or args.get(field) is None:
                return None
            try:
                return float(args[field])
            except (TypeError, ValueError):
                return None

        return cls(
            tool=spec.name,
            args=args,
            risk=spec.risk,
            side_effect=spec.side_effect,
            amount_usd=num(spec.amount_field),
            percent=num(spec.percent_field),
        )


@dataclass(frozen=True)
class ApprovalRequirement:
    required: bool
    min_role: Role | None
    reasons: tuple[str, ...]


NOT_REQUIRED = ApprovalRequirement(False, None, ())


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,.2f}"


def evaluate_approval(action: ProposedAction, autonomy: Autonomy, policies: WorkflowPolicies) -> ApprovalRequirement:
    if not action.side_effect:
        return NOT_REQUIRED

    reasons: list[str] = []
    role: Role | None = None

    def need(minimum: Role, reason: str) -> None:
        nonlocal role
        reasons.append(reason)
        if role is None or minimum.rank > role.rank:
            role = minimum

    if autonomy is Autonomy.suggest:
        need(Role.operator, "agent autonomy is 'suggest'")
    elif autonomy is Autonomy.act_with_approval and action.risk is not RiskLevel.low:
        need(Role.operator, f"agent autonomy requires approval for {action.risk.value}-risk actions")

    if action.risk is RiskLevel.high:
        need(Role.operator, f"{action.tool} is a high-risk action")

    if action.percent is not None and action.percent > policies.discount_pct_over:
        need(Role.operator, f"discount {action.percent:g}% exceeds {policies.discount_pct_over:g}% policy")

    if action.amount_usd is not None and "refund" in action.tool:
        if action.amount_usd > policies.admin_refund_usd_over:
            need(
                Role.admin,
                f"refund ${_fmt(action.amount_usd)} exceeds ${_fmt(policies.admin_refund_usd_over)} admin threshold",
            )
        elif action.amount_usd > policies.refund_usd_over:
            need(Role.operator, f"refund ${_fmt(action.amount_usd)} exceeds ${_fmt(policies.refund_usd_over)} policy")

    if action.amount_usd is not None and action.amount_usd > policies.owner_amount_usd_over:
        need(
            Role.owner,
            f"amount ${_fmt(action.amount_usd)} exceeds ${_fmt(policies.owner_amount_usd_over)} owner threshold",
        )

    if role is None:
        return NOT_REQUIRED
    return ApprovalRequirement(True, role, tuple(reasons))
