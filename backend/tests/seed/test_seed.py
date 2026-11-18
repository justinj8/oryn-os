from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from oryn.core.db import owner_session, tenant_session
from oryn.metrics.service import overview
from oryn.models import Agent, Outcome, Run, SbInvoice, Tenant, User, Workflow, WorkflowVersion
from oryn.seed.backfill import backfill
from oryn.seed.fixtures import seed_base
from oryn.workflows.dsl import WorkflowDefinition, validate_definition
from tests.orchestration.wf_helpers import worker


async def _counts() -> dict[str, int]:
    async with owner_session() as s:
        return {
            m.__name__: (await s.execute(select(func.count()).select_from(m))).scalar_one()
            for m in (Tenant, User, Agent, Workflow, SbInvoice)
        }


async def test_seed_base_idempotent() -> None:
    first = await seed_base()
    c1 = await _counts()
    await seed_base()
    assert await _counts() == c1
    assert {t.slug for t in first.tenants} == {"northwind", "brightsmile"}
    assert c1["Tenant"] == 2 and c1["User"] == 10 and c1["Agent"] == 8


async def test_seeded_workflows_validate() -> None:
    await seed_base()
    async with owner_session() as s:
        versions = (await s.execute(select(WorkflowVersion))).scalars().all()
    assert len(versions) >= 6
    for v in versions:
        assert validate_definition(WorkflowDefinition.model_validate(v.definition)) == []
        assert v.source_text  # every seeded workflow was compiled from plain English


async def test_backfill_small(isolated_temporal_env, acts) -> None:
    env = isolated_temporal_env
    summary = await seed_base()
    north = next(t for t in summary.tenants if t.slug == "northwind")
    async with worker(env.client, acts):
        result = await backfill(env.client, days=1, events_per_day=(3, 3), seed=7, tenants=["northwind"])
    assert result.runs_started >= 3
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date()
    async with owner_session() as s:
        runs = (await s.execute(select(Run).where(Run.tenant_id == north.id))).scalars().all()
        outcomes = (await s.execute(select(func.count()).select_from(Outcome))).scalar_one()
    assert runs and all(r.started_at.date() == yesterday for r in runs)
    assert all(r.status in ("completed", "escalated", "failed") for r in runs)
    assert outcomes > 0
    async with tenant_session(north.id) as s:
        m = await overview(s, 7)
    assert m.runs_total == len(runs) and m.llm_cost_usd > 0
