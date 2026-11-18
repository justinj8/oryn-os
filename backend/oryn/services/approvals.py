"""Human decisions on approvals. Shared by the API route and the demo manager script."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import update
from temporalio.client import Client

from oryn.api.deps import TenantContext
from oryn.core.audit import record_audit
from oryn.core.db import tenant_session
from oryn.core.tenancy import role_at_least
from oryn.models import Approval, ApprovalStatus, Run
from oryn.observability.bus import LiveEvent, get_event_bus
from oryn.orchestration.models import ApprovalDecisionSignal


class DecisionError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


async def decide(
    client: Client, ctx: TenantContext, approval_id: uuid.UUID, approved: bool, comment: str | None
) -> Approval:
    async with tenant_session(ctx.tenant_id) as s:
        a = await s.get(Approval, approval_id)
        if a is None:
            raise DecisionError(404, "approval not found")
        if not role_at_least(ctx.role, a.min_role):
            raise DecisionError(403, f"this approval requires role {a.min_role.value} or higher")
        run = await s.get(Run, a.run_id)
        if run and ctx.user_id and run.started_by_user_id == ctx.user_id:
            raise DecisionError(403, "you started this run, so someone else must approve it")
        # Atomic compare-and-set: exactly one decision can win, however many people click.
        new = ApprovalStatus.approved if approved else ApprovalStatus.rejected
        won = (
            await s.execute(
                update(Approval)
                .where(Approval.id == approval_id, Approval.status == ApprovalStatus.pending)
                .values(status=new, decided_by=ctx.user_id, decided_at=datetime.now(UTC), comment=comment)
                .returning(Approval.id)
            )
        ).scalar_one_or_none()
        if won is None:
            raise DecisionError(409, f"already {a.status.value}")
        await record_audit(
            s,
            ctx,
            f"approval.{new.value}",
            "approval",
            approval_id,
            before={"status": "pending"},
            after={"status": new.value, "comment": comment},
        )
        await s.refresh(a)
        workflow_id = run.temporal_workflow_id if run else None
    if workflow_id:
        await client.get_workflow_handle(workflow_id).signal(
            "decide_approval",
            ApprovalDecisionSignal(approval_id=approval_id, approved=approved, decided_by=ctx.user_id, comment=comment),
        )
    await get_event_bus().publish(
        LiveEvent(
            type="approval.decided",
            tenant_id=ctx.tenant_id,
            run_id=a.run_id,
            data={"approval_id": str(approval_id), "status": new.value},
        )
    )
    return a
