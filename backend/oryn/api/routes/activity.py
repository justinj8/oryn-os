"""The activity feed: what happened that a person should know about, newest first.

Quiet successes are left out on purpose. The feed shows failures, escalations, approvals asked
for and decided, and business outcomes, so it reads like a list of things worth a glance.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from oryn.api.deps import TenantContext, require_role
from oryn.core.db import tenant_session
from oryn.core.tenancy import Role
from oryn.models import Approval, ApprovalStatus, Outcome, Run, RunStatus

router = APIRouter(prefix="/api", tags=["activity"])

Kind = Literal["approval_requested", "approval_decided", "run_failed", "run_escalated", "outcome"]


class ActivityItem(BaseModel):
    id: str
    kind: Kind
    at: datetime
    title: str
    detail: str | None = None
    href: str
    value_usd: float | None = None
    tone: Literal["hold", "fail", "divert", "clear", "neutral"]


@router.get("/activity", response_model=list[ActivityItem])
async def activity(
    limit: int = Query(30, ge=1, le=100),
    before: datetime | None = Query(None, description="Only items strictly older than this (for paging)"),
    ctx: TenantContext = Depends(require_role(Role.viewer)),
) -> list[ActivityItem]:
    items: list[ActivityItem] = []
    async with tenant_session(ctx.tenant_id) as s:
        # Approvals asked for (still pending or not: asking is the news).
        asked = select(Approval, Run.title).join(Run, Run.id == Approval.run_id)
        if before:
            asked = asked.where(Approval.requested_at < before)
        for a, title in await s.execute(asked.order_by(Approval.requested_at.desc()).limit(limit)):
            pending = a.status == ApprovalStatus.pending
            items.append(
                ActivityItem(
                    id=f"approval_requested:{a.id}",
                    kind="approval_requested",
                    at=a.requested_at,
                    title=a.description or "Approval requested",
                    detail=title,
                    href="/approvals" if pending else f"/runs/{a.run_id}",
                    tone="hold",
                )
            )

        # Decisions people made.
        decided = (
            select(Approval, Run.title).join(Run, Run.id == Approval.run_id).where(Approval.decided_at.is_not(None))
        )
        if before:
            decided = decided.where(Approval.decided_at < before)
        for d, title in await s.execute(decided.order_by(Approval.decided_at.desc()).limit(limit)):
            assert d.decided_at is not None
            items.append(
                ActivityItem(
                    id=f"approval_decided:{d.id}",
                    kind="approval_decided",
                    at=d.decided_at,
                    title=f"{d.status.value.replace('_', ' ').capitalize()}: {d.description}",
                    detail=d.comment or title,
                    href=f"/runs/{d.run_id}",
                    tone="clear" if d.status == ApprovalStatus.approved else "neutral",
                )
            )

        # Runs that failed or were handed to a person.
        ended = func.coalesce(Run.ended_at, Run.started_at)
        troubled = select(Run, ended).where(Run.status.in_([RunStatus.failed, RunStatus.escalated]))
        if before:
            troubled = troubled.where(ended < before)
        for r, at in await s.execute(troubled.order_by(ended.desc()).limit(limit)):
            failed = r.status == RunStatus.failed
            items.append(
                ActivityItem(
                    id=f"run:{r.id}",
                    kind="run_failed" if failed else "run_escalated",
                    at=at,
                    title=r.title or "Untitled run",
                    detail=r.error if failed else "Handed to a person",
                    href=f"/runs/{r.id}",
                    tone="fail" if failed else "divert",
                )
            )

        # Business outcomes.
        outcomes = select(Outcome, Run.title).join(Run, Run.id == Outcome.run_id)
        if before:
            outcomes = outcomes.where(Outcome.occurred_at < before)
        for o, title in await s.execute(outcomes.order_by(Outcome.occurred_at.desc()).limit(limit)):
            value = float(o.value_usd)
            items.append(
                ActivityItem(
                    id=f"outcome:{o.id}",
                    kind="outcome",
                    at=o.occurred_at,
                    title=o.type.value.replace("_", " ").capitalize(),
                    detail=title,
                    href=f"/runs/{o.run_id}",
                    value_usd=value or None,
                    tone="clear",
                )
            )

    items.sort(key=lambda i: i.at, reverse=True)
    return items[:limit]
