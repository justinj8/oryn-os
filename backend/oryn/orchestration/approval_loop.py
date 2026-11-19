"""The durable approval wait, shared by run workflows, conversations and MCP actions.

Runs *inside workflow code*: it only calls activities, timers and the pure
``next_escalation`` function, so it is replay-safe.

    request_approval ─▶ wait(decision | timeout) ─┬─ decision ───────────▶ approved / rejected
                              ▲                    └─ timeout ─▶ next_escalation
                              └──────── escalate (higher role, longer wait) ◀┘   └▶ auto-reject
"""

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from oryn.core.tenancy import Role
    from oryn.models import ApprovalStatus, RunStatus
    from oryn.orchestration.activities import OrynActivities
    from oryn.orchestration.models import (
        ApprovalDecisionSignal,
        MarkRunInput,
        RequestApprovalInput,
        SpanEventInput,
        UpdateApprovalInput,
    )
    from oryn.orchestration.retry import QUICK_RETRY, QUICK_START_TO_CLOSE
    from oryn.policies.escalation import EscalationPolicy, next_escalation


@dataclass
class ApprovalLoopCtx:
    tenant_id: uuid.UUID
    run_id: uuid.UUID
    time_offset_seconds: float
    time_scale: float
    escalation: EscalationPolicy
    decision: Callable[[uuid.UUID], ApprovalDecisionSignal | None]
    add_pending: Callable[[uuid.UUID], None]
    remove_pending: Callable[[uuid.UUID], None]
    cancelled: Callable[[], bool]


@dataclass
class ApprovalResult:
    approved: bool
    cancelled: bool
    comment: str | None
    approval_id: uuid.UUID


async def _quick(fn, arg) -> object:
    return await workflow.execute_activity_method(
        fn, arg, start_to_close_timeout=QUICK_START_TO_CLOSE, retry_policy=QUICK_RETRY
    )


async def run_approval_loop(
    ctx: ApprovalLoopCtx,
    *,
    step_id: str,
    tool: str | None,
    args: dict,
    idempotency_key: str,
    description: str,
    reasons: list[str],
    min_role: Role,
    agent_id: uuid.UUID | None = None,
) -> ApprovalResult:
    base = dict(tenant_id=ctx.tenant_id, run_id=ctx.run_id, time_offset_seconds=ctx.time_offset_seconds)
    timeout = ctx.escalation.timeout_seconds
    approval_id = await workflow.execute_activity_method(
        OrynActivities.request_approval,
        RequestApprovalInput(
            **base,
            step_id=step_id,
            tool=tool,
            args=args,
            idempotency_key=idempotency_key,
            description=description,
            reasons=reasons,
            min_role=min_role,
            expires_in_s=timeout,
            agent_id=agent_id,
        ),
        start_to_close_timeout=QUICK_START_TO_CLOSE,
        retry_policy=QUICK_RETRY,
    )
    ctx.add_pending(approval_id)
    await _quick(OrynActivities.mark_run, MarkRunInput(**base, status=RunStatus.waiting_approval, current_step=step_id))
    role, level = min_role, 0
    try:
        while True:
            try:
                await workflow.wait_condition(
                    lambda: ctx.decision(approval_id) is not None or ctx.cancelled(),
                    timeout=timedelta(seconds=max(1.0, timeout / ctx.time_scale)),
                )
            except TimeoutError:
                d = next_escalation(role, level, ctx.escalation)
                if d.action == "escalate":
                    assert d.next_role is not None and d.timeout_seconds is not None
                    level, role, timeout = level + 1, d.next_role, d.timeout_seconds
                    current = await _quick(
                        OrynActivities.update_approval_status,
                        UpdateApprovalInput(
                            **base,
                            approval_id=approval_id,
                            status=ApprovalStatus.pending,
                            min_role=role,
                            escalation_level=level,
                            expires_in_s=timeout,
                        ),
                    )
                    if current in (ApprovalStatus.approved.value, ApprovalStatus.rejected.value):
                        # A person decided just before the timer fired; their decision stands.
                        return ApprovalResult(current == ApprovalStatus.approved.value, False, None, approval_id)
                    await _quick(
                        OrynActivities.record_span_event,
                        SpanEventInput(
                            **base,
                            kind="decision",
                            name=f"approval escalated to {role.value}",
                            data={"reason": d.reason},
                        ),
                    )
                    continue
                final = await _quick(
                    OrynActivities.update_approval_status,
                    UpdateApprovalInput(
                        **base, approval_id=approval_id, status=ApprovalStatus.rejected, comment=d.reason
                    ),
                )
                if final == ApprovalStatus.approved.value:  # a human approved in the same instant; honour it
                    return ApprovalResult(True, False, None, approval_id)
                return ApprovalResult(False, False, d.reason, approval_id)
            if ctx.cancelled():
                await _quick(
                    OrynActivities.update_approval_status,
                    UpdateApprovalInput(
                        **base, approval_id=approval_id, status=ApprovalStatus.cancelled, comment="run cancelled"
                    ),
                )
                return ApprovalResult(False, True, "run cancelled", approval_id)
            sig = ctx.decision(approval_id)
            assert sig is not None
            return ApprovalResult(sig.approved, False, sig.comment, approval_id)
    finally:
        ctx.remove_pending(approval_id)
        if not ctx.cancelled():
            await _quick(OrynActivities.mark_run, MarkRunInput(**base, status=RunStatus.running, current_step=step_id))


__all__ = ["ApprovalLoopCtx", "ApprovalResult", "asyncio", "run_approval_loop"]
