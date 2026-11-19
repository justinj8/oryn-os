from sqlalchemy import func, select

from oryn.core.db import owner_session
from oryn.models import Event, Run
from oryn.services.ingest import ingest_event
from tests.orchestration.wf_helpers import GOLDEN, LEAD
from tests.workflow_factory import make_workflow


async def test_duplicate_event_starts_one_run(tenant, temporal_env) -> None:
    await make_workflow(tenant, GOLDEN)
    r1 = await ingest_event(temporal_env.client, tenant.id, "lead.created", "web", LEAD, "lead-123")
    r2 = await ingest_event(temporal_env.client, tenant.id, "lead.created", "web", LEAD, "lead-123")
    assert r1.created and not r2.created
    assert len(r1.run_ids) == 1 and r2.run_ids == r1.run_ids and r2.event_id == r1.event_id
    async with owner_session() as s:
        assert (await s.execute(select(func.count()).select_from(Event))).scalar_one() == 1
        run = (await s.execute(select(Run))).scalar_one()
    desc = await temporal_env.client.get_workflow_handle(run.temporal_workflow_id).describe()
    assert desc.id == run.temporal_workflow_id
    assert run.title.startswith("Inbound lead to booked meeting")


async def test_trigger_filter_matching(tenant, temporal_env) -> None:
    await make_workflow(tenant, {**GOLDEN, "trigger": {"event": "lead.created", "filter": {"source": "web"}}})
    phone = await ingest_event(
        temporal_env.client,
        tenant.id,
        "lead.created",
        "phone",
        {**LEAD, "source": "phone"},
        "k-phone",
    )
    web = await ingest_event(temporal_env.client, tenant.id, "lead.created", "web", LEAD, "k-web")
    assert phone.run_ids == [] and len(web.run_ids) == 1


async def test_disabled_workflow_ignored(tenant, temporal_env) -> None:
    await make_workflow(tenant, GOLDEN, enabled=False)
    r = await ingest_event(temporal_env.client, tenant.id, "lead.created", "web", LEAD, "k1")
    assert r.created and r.run_ids == []


async def test_redelivery_restarts_a_run_that_failed_to_start(tenant, temporal_env) -> None:
    """Review finding I9: if starting the workflow failed, the run was marked failed and a provider's
    retry of the same event (same idempotency key) never tried again."""

    class FlakyClient:
        def __init__(self, inner) -> None:
            self.inner, self.calls = inner, 0

        async def start_workflow(self, *a, **kw):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporal unavailable")
            return await self.inner.start_workflow(*a, **kw)

        def __getattr__(self, name):
            return getattr(self.inner, name)

    await make_workflow(tenant, GOLDEN)
    flaky = FlakyClient(temporal_env.client)
    first = await ingest_event(flaky, tenant.id, "lead.created", "web", LEAD, "lead-flaky")
    async with owner_session() as s:
        assert (await s.get(Run, first.run_ids[0])).status == "failed"
    again = await ingest_event(flaky, tenant.id, "lead.created", "web", LEAD, "lead-flaky")
    assert not again.created and again.run_ids == first.run_ids
    async with owner_session() as s:
        run = await s.get(Run, first.run_ids[0])
    assert run.status == "running" and run.error is None
    desc = await temporal_env.client.get_workflow_handle(run.temporal_workflow_id).describe()
    assert desc.id == run.temporal_workflow_id
