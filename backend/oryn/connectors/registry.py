"""Builds the set of connectors a tenant's agents use for one unit of work."""

import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oryn.connectors.base import CRM, Billing, Calendar, Database, Docs, Messaging
from oryn.connectors.faults import FaultInjector
from oryn.connectors.sandbox.billing import SandboxBilling
from oryn.connectors.sandbox.calendar import SandboxCalendar
from oryn.connectors.sandbox.crm import SandboxCRM
from oryn.connectors.sandbox.database import SandboxDatabase
from oryn.connectors.sandbox.docs import SandboxDocs
from oryn.connectors.sandbox.messaging import SandboxMessaging
from oryn.core.config import Settings
from oryn.models import Connector, ConnectorKind, Tenant


@dataclass
class ConnectorSet:
    crm: CRM
    calendar: Calendar
    billing: Billing
    messaging: Messaging
    database: Database
    docs: Docs


async def build_connector_set(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    settings: Settings,
    now: Callable[[], datetime] | None = None,
    rng: random.Random | None = None,
    attempt: int = 1,
) -> ConnectorSet:
    now = now or (lambda: datetime.now(UTC))
    rng = rng or random.Random()
    rows = (await session.execute(select(Connector))).scalars().all()
    by_kind = {c.kind: c for c in rows}
    tenant = await session.get(Tenant, tenant_id)
    tz = (tenant.settings or {}).get("timezone", "America/New_York") if tenant else "America/New_York"

    def faults(kind: ConnectorKind) -> FaultInjector:
        cfg = by_kind[kind].settings if kind in by_kind else {}
        return FaultInjector(
            float(cfg.get("failure_rate", settings.sandbox_failure_rate)),
            int(cfg.get("latency_ms", settings.sandbox_latency_ms)),
            rng,
            fail_attempts=int(cfg.get("fail_attempts", 0)),
            attempt=attempt,
        )

    messaging: Messaging = SandboxMessaging(session, tenant_id, faults(ConnectorKind.email), now=now)
    messaging = _real_messaging(settings, messaging)
    return ConnectorSet(
        crm=SandboxCRM(session, tenant_id, faults(ConnectorKind.crm)),
        calendar=SandboxCalendar(session, tenant_id, faults(ConnectorKind.calendar), tz=tz, now=now),
        billing=SandboxBilling(session, tenant_id, faults(ConnectorKind.billing), today=lambda: now().date()),
        messaging=messaging,
        database=SandboxDatabase(session, tenant_id, faults(ConnectorKind.database)),
        docs=SandboxDocs(session, tenant_id, faults(ConnectorKind.docs)),
    )


def _real_messaging(settings: Settings, sandbox: Messaging) -> Messaging:
    """Hook for real providers (Twilio/SMTP), filled in by the channels module."""
    return sandbox
