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

    messaging = _real_messaging(settings, SandboxMessaging(session, tenant_id, faults(ConnectorKind.email), now=now))
    return ConnectorSet(
        crm=SandboxCRM(session, tenant_id, faults(ConnectorKind.crm)),
        calendar=SandboxCalendar(session, tenant_id, faults(ConnectorKind.calendar), tz=tz, now=now),
        billing=SandboxBilling(session, tenant_id, faults(ConnectorKind.billing), today=lambda: now().date()),
        messaging=messaging,
        database=SandboxDatabase(session, tenant_id, faults(ConnectorKind.database)),
        docs=SandboxDocs(session, tenant_id, faults(ConnectorKind.docs)),
    )


class CompositeMessaging:
    """Routes each channel to its provider: real Twilio/SMTP when configured, else the sandbox."""

    def __init__(self, sms, email, chat: SandboxMessaging) -> None:
        self.sms, self.email, self.chat = sms, email, chat

    @property
    def provider(self) -> str:
        return f"sms={self.sms.provider},email={self.email.provider}"

    async def send_sms(self, to, body, idempotency_key, conversation_id=None):
        return await self.sms.send_sms(to, body, idempotency_key, conversation_id)

    async def send_email(self, to, subject, body, idempotency_key, conversation_id=None):
        return await self.email.send_email(to, subject, body, idempotency_key, conversation_id)

    async def send_chat(self, conversation_id, body, idempotency_key):
        return await self.chat.send_chat(conversation_id, body, idempotency_key)


def _real_messaging(settings: Settings, sandbox: SandboxMessaging) -> Messaging:
    sms: object = sandbox
    email: object = sandbox
    if settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number:
        from oryn.connectors.twilio import TwilioMessaging

        sms = TwilioMessaging(
            settings.twilio_account_sid,
            settings.twilio_auth_token.get_secret_value(),
            settings.twilio_from_number,
            sandbox,
        )
    if settings.smtp_url:
        from oryn.connectors.smtp import SmtpMessaging

        email = SmtpMessaging(settings.smtp_url, settings.smtp_from, sandbox)
    return CompositeMessaging(sms, email, sandbox)
