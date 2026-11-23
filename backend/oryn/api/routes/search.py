"""One search box for the whole workspace: what the dashboard's command palette queries."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from oryn.api.deps import TenantContext, require_role
from oryn.api.routes.runs import title_matches
from oryn.core.db import tenant_session
from oryn.core.tenancy import Role
from oryn.models import Agent, Approval, ApprovalStatus, Run, Workflow

router = APIRouter(prefix="/api", tags=["search"])


class SearchHit(BaseModel):
    kind: Literal["approval", "run", "agent", "workflow"]
    id: str
    title: str
    subtitle: str
    href: str


@router.get("/search", response_model=list[SearchHit])
async def search(
    q: str = Query("", max_length=200),
    limit: int = Query(5, ge=1, le=20, description="Maximum hits per kind"),
    ctx: TenantContext = Depends(require_role(Role.viewer)),
) -> list[SearchHit]:
    """Pending approvals first (they need a person), then runs, agents and workflows. RLS scopes every query."""
    if not q.strip():
        return []
    hits: list[SearchHit] = []
    async with tenant_session(ctx.tenant_id) as s:
        approvals = await s.execute(
            select(Approval)
            .where(Approval.status == ApprovalStatus.pending, title_matches(Approval.description, q))
            .order_by(Approval.requested_at.desc())
            .limit(limit)
        )
        hits += [
            SearchHit(
                kind="approval",
                id=str(a.id),
                title=a.description,
                subtitle=f"Waiting for {a.min_role.value} approval",
                href="/approvals",
            )
            for a in approvals.scalars()
        ]
        runs = await s.execute(
            select(Run).where(title_matches(Run.title, q)).order_by(Run.started_at.desc()).limit(limit)
        )
        hits += [
            SearchHit(
                kind="run",
                id=str(r.id),
                title=r.title or "Untitled run",
                subtitle=r.status.value.replace("_", " ").capitalize(),
                href=f"/runs/{r.id}",
            )
            for r in runs.scalars()
        ]
        agents = await s.execute(select(Agent).where(title_matches(Agent.name, q)).order_by(Agent.name).limit(limit))
        hits += [
            SearchHit(
                kind="agent",
                id=str(a.id),
                title=a.name,
                subtitle=f"{a.role.value.capitalize()} agent",
                href="/agents",
            )
            for a in agents.scalars()
        ]
        workflows = await s.execute(
            select(Workflow).where(title_matches(Workflow.name, q)).order_by(Workflow.name).limit(limit)
        )
        hits += [
            SearchHit(
                kind="workflow",
                id=str(w.id),
                title=w.name,
                subtitle=f"Runs on {w.trigger_event}",
                href=f"/workflows/{w.id}",
            )
            for w in workflows.scalars()
        ]
    return hits
