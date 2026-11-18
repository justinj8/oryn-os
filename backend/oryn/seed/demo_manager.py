"""A scripted 'manager' who answers approvals during the history backfill, through the same
decision path (and audit trail) a person uses in the dashboard."""

import random
import uuid
from datetime import timedelta

from sqlalchemy import select
from temporalio.client import Client

from oryn.api.deps import TenantContext
from oryn.core.db import tenant_session
from oryn.core.tenancy import Role, role_at_least
from oryn.models import Approval, ApprovalStatus, Membership, User
from oryn.services.approvals import DecisionError, decide


async def manager_context(tenant_id: uuid.UUID, slug: str) -> TenantContext:
    async with tenant_session(tenant_id) as s:
        row = (
            await s.execute(
                select(User.id, Membership.role)
                .join(Membership, Membership.user_id == User.id)
                .where(User.email == f"demo.manager@{slug}.test")
            )
        ).one()
    return TenantContext(tenant_id=tenant_id, user_id=row[0], role=Role(row[1]), via="user")


async def decide_pending(client: Client, ctx: TenantContext, rng: random.Random, approve_rate: float = 0.8) -> int:
    async with tenant_session(ctx.tenant_id) as s:
        pending = (await s.execute(select(Approval).where(Approval.status == ApprovalStatus.pending))).scalars().all()
    decided = 0
    for a in pending:
        if not role_at_least(ctx.role, a.min_role):
            continue  # above the manager's pay grade: let it escalate (and possibly time out)
        approved = rng.random() < approve_rate
        when = a.requested_at + timedelta(minutes=rng.randint(2, 45))
        try:
            await decide(client, ctx, a.id, approved, None if approved else "Not this time.", decided_at=when)
            decided += 1
        except DecisionError:
            pass  # already decided or timed out meanwhile
    return decided
