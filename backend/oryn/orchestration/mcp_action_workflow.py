"""McpActionWorkflow — a side-effecting tool call from an external MCP client, held for approval.

MCP clients are outside our trust boundary, so every side-effecting tool they call goes through
the same durable approval loop as agent actions, then the same idempotent ``execute_action``."""

import uuid
from typing import Any

from pydantic import BaseModel
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from oryn.core.tenancy import Role
    from oryn.models import RunStatus
    from oryn.orchestration.activities import OrynActivities
    from oryn.orchestration.approval_loop import ApprovalLoopCtx, run_approval_loop
    from oryn.orchestration.models import ApprovalDecisionSignal, ExecuteActionInput, FinalizeInput
    from oryn.orchestration.retry import ACTION_RETRY, ACTION_START_TO_CLOSE, QUICK_RETRY, QUICK_START_TO_CLOSE
    from oryn.policies.escalation import EscalationPolicy


class McpActionInput(BaseModel):
    tenant_id: uuid.UUID
    run_id: uuid.UUID
    tool: str
    args: dict[str, Any]
    idempotency_key: str
    description: str
    reasons: list[str]
    min_role: Role


@workflow.defn(name="McpActionWorkflow")
class McpActionWorkflow:
    def __init__(self) -> None:
        self.pending = None
        self.decisions: dict[Any, ApprovalDecisionSignal] = {}
        self.cancelled = False

    @workflow.signal
    def decide_approval(self, sig: ApprovalDecisionSignal) -> None:
        if sig.approval_id not in self.decisions:  # record every decision by id, once
            self.decisions[sig.approval_id] = sig

    @workflow.signal
    def cancel(self) -> None:
        self.cancelled = True

    def _add_pending(self, approval_id) -> None:
        self.pending = approval_id

    def _remove_pending(self, approval_id) -> None:
        self.pending = None

    @workflow.run
    async def run(self, inp: McpActionInput) -> dict[str, Any]:
        ctx = ApprovalLoopCtx(
            tenant_id=inp.tenant_id,
            run_id=inp.run_id,
            time_offset_seconds=0,
            time_scale=1.0,
            escalation=EscalationPolicy(),
            decision=lambda a: self.decisions.get(a),
            add_pending=self._add_pending,
            remove_pending=self._remove_pending,
            cancelled=lambda: self.cancelled,
        )
        r = await run_approval_loop(
            ctx,
            step_id="mcp",
            tool=inp.tool,
            args=inp.args,
            idempotency_key=inp.idempotency_key,
            description=inp.description,
            reasons=inp.reasons,
            min_role=inp.min_role,
        )
        base = {"tenant_id": inp.tenant_id, "run_id": inp.run_id}
        if r.approved:
            result = await workflow.execute_activity_method(
                OrynActivities.execute_action,
                ExecuteActionInput(
                    **base, agent_id=None, tool=inp.tool, args=inp.args, idempotency_key=inp.idempotency_key
                ),
                start_to_close_timeout=ACTION_START_TO_CLOSE,
                retry_policy=ACTION_RETRY,
            )
            out, status, summary = {"status": "executed", "result": result}, RunStatus.completed, f"{inp.tool} executed"
        else:
            out = {"status": "cancelled" if r.cancelled else "rejected", "comment": r.comment}
            status = RunStatus.cancelled if r.cancelled else RunStatus.completed
            summary = f"{inp.tool} not approved" + (f": {r.comment}" if r.comment else "")
        await workflow.execute_activity_method(
            OrynActivities.finalize_run,
            FinalizeInput(**base, status=status, summary=summary),
            start_to_close_timeout=QUICK_START_TO_CLOSE,
            retry_policy=QUICK_RETRY,
        )
        return out
