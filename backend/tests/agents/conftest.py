import random
import uuid
from datetime import UTC, datetime

import pytest

from oryn.agents.runner import AgentDeps
from oryn.connectors.registry import build_connector_set
from oryn.core.config import Settings
from oryn.core.db import owner_session, tenant_session
from oryn.llm.replay.provider import ReplayProvider
from oryn.memory.embeddings import HashingEmbedder
from oryn.memory.store import MemoryStore
from oryn.models import Agent, AgentRole, Autonomy, Run
from oryn.tools.registry import default_registry
from tests.factories import make_tenant
from tests.fakes import FakeSpanSink

NOW = datetime(2026, 11, 16, 13, 0, tzinfo=UTC)
LEAD = {
    "name": "Dana Reyes",
    "email": "dana@example.com",
    "phone": "+15550101",
    "company": "Reyes Co",
    "need": "heat pump install",
    "budget_usd": 8200,
    "requested_discount_pct": 15,
    "source": "web",
}


@pytest.fixture
async def world():
    t = await make_tenant("acme", timezone="America/New_York")
    run_id = uuid.uuid4()
    async with owner_session() as s:
        s.add_all(
            [
                Agent(
                    tenant_id=t.id,
                    name="Sales",
                    role=AgentRole.sales,
                    autonomy=Autonomy.autonomous,
                    allowed_tools=["crm.*"],
                ),
                Agent(
                    tenant_id=t.id,
                    name="Scheduler",
                    role=AgentRole.scheduler,
                    autonomy=Autonomy.autonomous,
                    allowed_tools=["calendar.*", "messaging.*", "crm.get_contact"],
                ),
            ]
        )
        s.add(Run(id=run_id, tenant_id=t.id, temporal_workflow_id=f"wf-{run_id}", started_at=NOW, title="t"))
    return t, run_id


def make_deps(session, connectors, llm=None, sink=None) -> AgentDeps:
    return AgentDeps(
        llm=llm or ReplayProvider(),
        registry=default_registry(),
        memory=MemoryStore(HashingEmbedder()),
        spans=sink or FakeSpanSink(),
        session=session,
        connectors=connectors,
        settings=Settings(),
    )


@pytest.fixture
def session_for():
    async def _open(tenant_id):
        cm = tenant_session(tenant_id)
        s = await cm.__aenter__()
        cs = await build_connector_set(s, tenant_id, Settings(), now=lambda: NOW, rng=random.Random(1))
        return cm, s, cs

    return _open
