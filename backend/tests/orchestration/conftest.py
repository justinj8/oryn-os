import uuid
from datetime import UTC, datetime

import pytest

from oryn.core.db import owner_session
from oryn.models import (
    Agent,
    AgentRole,
    Autonomy,
    Connector,
    ConnectorKind,
    Run,
    SbContact,
    SbDocument,
    SbInvoice,
)
from oryn.orchestration.activities import OrynActivities
from tests.factories import make_tenant


@pytest.fixture
async def tenant():
    t = await make_tenant("acme", timezone="America/New_York")
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
                    allowed_tools=["calendar.*", "messaging.*"],
                ),
                Agent(
                    tenant_id=t.id,
                    name="Support",
                    role=AgentRole.support,
                    autonomy=Autonomy.autonomous,
                    allowed_tools=["docs.*", "db.query", "billing.*", "crm.find_contact"],
                ),
                Agent(
                    tenant_id=t.id,
                    name="Reporting",
                    role=AgentRole.reporting,
                    autonomy=Autonomy.autonomous,
                    allowed_tools=["db.query", "messaging.send_email"],
                ),
            ]
        )
        s.add(Connector(tenant_id=t.id, kind=ConnectorKind.calendar, provider="sandbox", name="Calendar"))
        s.add(SbDocument(tenant_id=t.id, title="Refund policy", body="Refunds within 30 days of service."))
    return t


@pytest.fixture
async def run_row(tenant):
    rid = uuid.uuid4()
    async with owner_session() as s:
        s.add(
            Run(
                id=rid,
                tenant_id=tenant.id,
                temporal_workflow_id=f"wf-{rid}",
                started_at=datetime.now(UTC),
                title="test run",
            )
        )
    return rid


@pytest.fixture
async def invoice(tenant):
    async with owner_session() as s:
        c = SbContact(tenant_id=tenant.id, name="Ann Lee", email="ann@example.com", phone="+15550199")
        s.add(c)
        await s.flush()
        inv = SbInvoice(
            tenant_id=tenant.id,
            contact_id=c.id,
            number="INV-1001",
            amount_usd=300,
            status="open",
            due_date=datetime(2026, 11, 1).date(),
        )
        s.add(inv)
        await s.flush()
        return inv.id


@pytest.fixture
def acts() -> OrynActivities:
    return OrynActivities.default()
