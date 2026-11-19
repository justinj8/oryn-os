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
    from oryn.core.config import get_settings
    from oryn.orchestration.worker import backfill_queue

    async with worker(env.client, acts), worker(env.client, acts, queue=backfill_queue(get_settings())):
        result = await backfill(
            env.client, days=1, events_per_day=(3, 3), seed=7, tenants=["northwind"], scheduled=False
        )  # date-independent: no weekly/overdue events
    assert result.runs_started >= 3
    # History runs on its own queue, so live demo traffic never waits behind the backfill.
    async with owner_session() as s:
        wf_id = (await s.execute(select(Run.temporal_workflow_id).limit(1))).scalar_one()
    desc = await env.client.get_workflow_handle(wf_id).describe()
    assert desc.task_queue == backfill_queue(get_settings())
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date()
    async with owner_session() as s:
        runs = (await s.execute(select(Run).where(Run.tenant_id == north.id))).scalars().all()
        outcomes = (await s.execute(select(func.count()).select_from(Outcome))).scalar_one()
    assert runs and all(r.started_at.date() == yesterday for r in runs)
    assert all(r.status in ("completed", "escalated", "failed") for r in runs), [
        (r.title, r.status, r.error) for r in runs
    ]
    assert outcomes > 0
    async with tenant_session(north.id) as s:
        m = await overview(s, 7)
    assert m.runs_total == len(runs) and m.llm_cost_usd > 0


async def test_demo_manager_only_decides_backfill_approvals(temporal_env) -> None:
    """Regression: the scripted manager approved a live demo user's pending discount mid-backfill."""
    import random
    import uuid as _uuid

    from oryn.core.tenancy import Role
    from oryn.models import Approval, Event
    from oryn.seed.demo_manager import decide_pending, manager_context

    summary = await seed_base()
    north = next(t for t in summary.tenants if t.slug == "northwind")
    ids = {}
    async with owner_session() as s:
        for source in ("backfill", "simulator"):
            ev = Event(
                id=_uuid.uuid4(),
                tenant_id=north.id,
                type="lead.created",
                source=source,
                idempotency_key=f"k-{source}",
                payload={},
            )
            s.add(ev)
            await s.flush()
            run = Run(
                id=_uuid.uuid4(),
                tenant_id=north.id,
                temporal_workflow_id=f"wf-{source}",
                trigger_event_id=ev.id,
                started_at=datetime.now(UTC),
            )
            s.add(run)
            await s.flush()
            a = Approval(
                tenant_id=north.id,
                run_id=run.id,
                step_id="s",
                idempotency_key=f"a-{source}",
                min_role=Role.operator,
                status="pending",
                requested_at=datetime.now(UTC),
            )
            s.add(a)
            await s.flush()
            ids[source] = a.id
    ctx = await manager_context(north.id, "northwind")
    await decide_pending(temporal_env.client, ctx, random.Random(1), approve_rate=1.0)
    async with owner_session() as s:
        assert (await s.get(Approval, ids["backfill"])).status != "pending"
        assert (await s.get(Approval, ids["simulator"])).status == "pending"
