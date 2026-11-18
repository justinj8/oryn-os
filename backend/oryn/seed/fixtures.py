"""Demo tenants, people, agents, connectors, workflows and sandbox data. Idempotent."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from oryn.builder.examples import EXAMPLES
from oryn.builder.grammar import compile_offline
from oryn.core.db import owner_session
from oryn.core.security import hash_password
from oryn.core.tenancy import Role
from oryn.models import (
    Agent,
    AgentRole,
    Autonomy,
    Connector,
    ConnectorKind,
    Membership,
    SbContact,
    SbDocument,
    SbInvoice,
    Tenant,
    User,
    Workflow,
    WorkflowVersion,
)

DEMO_PASSWORD = "oryn-demo"  # local demo only; documented in the README

PEOPLE = [
    ("owner", "Olivia Owner", Role.owner),
    ("admin", "Adam Admin", Role.admin),
    ("operator", "Priya Operator", Role.operator),
    ("viewer", "Victor Viewer", Role.viewer),
    ("demo.manager", "Demo Manager", Role.admin),
]

AGENTS = {
    "northwind": [
        (
            "Sales",
            AgentRole.sales,
            ["crm.*", "docs.search"],
            ["chat", "email"],
            "You sell HVAC installs and service plans. Qualify on budget and need; never promise a discount yourself.",
        ),
        (
            "Scheduler",
            AgentRole.scheduler,
            ["calendar.*", "messaging.*", "crm.get_contact"],
            ["chat", "sms", "voice"],
            "You book on-site visits and consultations in business hours.",
        ),
        (
            "Support",
            AgentRole.support,
            ["docs.search", "db.query", "billing.*", "crm.find_contact"],
            ["chat", "sms", "email"],
            "Answer from the knowledge base. Refunds follow the refund policy.",
        ),
        (
            "Billing ops",
            AgentRole.ops,
            ["billing.*", "crm.get_contact", "messaging.send_sms"],
            [],
            "Chase overdue invoices politely.",
        ),
        ("Reporting", AgentRole.reporting, ["db.query", "messaging.send_email"], [], "Weekly KPI summaries."),
    ],
    "brightsmile": [
        (
            "Front desk",
            AgentRole.scheduler,
            ["calendar.*", "messaging.*", "crm.*"],
            ["chat", "sms", "voice"],
            "You book dental appointments; mornings fill up fastest.",
        ),
        (
            "Patient support",
            AgentRole.support,
            ["docs.search", "db.query", "billing.*", "crm.find_contact"],
            ["chat", "sms", "email"],
            "Answer insurance and policy questions from the knowledge base.",
        ),
        ("Reporting", AgentRole.reporting, ["db.query", "messaging.send_email"], [], "Weekly practice summary."),
    ],
}

WORKFLOW_TEXT = {
    "northwind": EXAMPLES[:4],
    "brightsmile": [
        "When a new lead arrives, have the scheduling agent book a new patient cleaning appointment. Wait 2 hours, "
        "then send them an appointment reminder.",
        EXAMPLES[1],
        EXAMPLES[3],
    ],
}

DOCS = {
    "northwind": [
        (
            "Refund policy",
            "Refunds are available within 30 days of service. Parts are refundable if unused; labor is "
            "refundable when the repair did not resolve the issue.",
        ),
        ("Business hours", "We're open Monday to Friday, 8am to 6pm, with 24/7 emergency service for no-heat calls."),
        ("Maintenance plan", "The Comfort Plan is $189/year: two tune-ups, priority scheduling and 15% off repairs."),
        (
            "Furnace noise troubleshooting",
            "Banging or rattling usually means a loose panel or ignition delay. Turn "
            "the system off and book a technician visit; it's covered under the Comfort Plan.",
        ),
    ],
    "brightsmile": [
        ("Cancellation policy", "Please give 24 hours notice to cancel; late cancellations may incur a $50 fee."),
        (
            "Insurance",
            "We accept most PPO plans including Delta Dental, Cigna and Aetna. We'll verify before your visit.",
        ),
        ("Office hours", "Monday to Thursday 7am to 5pm, Friday 7am to 1pm."),
        (
            "Tooth pain",
            "For tooth pain, rinse with warm salt water and call us — same-day emergency slots are held every morning.",
        ),
    ],
}

CONTACTS = [
    ("Ann Lee", "ann.lee@example.com", "+15550199", "Lee Bakery"),
    ("Marcus Johnson", "marcus.j@example.com", "+15550142", None),
    ("Sofia Garcia", "sofia@garcia-realty.com", "+15550177", "Garcia Realty"),
    ("Kwame Okafor", "kwame@okafor.dev", "+15550133", None),
    ("Grace Kim", "grace.kim@example.com", "+15550155", "Kim Studio"),
    ("Diego Silva", "diego@silva.co", "+15550166", "Silva & Co"),
]


@dataclass
class SeedSummary:
    tenants: list[Tenant] = field(default_factory=list)
    created: list[str] = field(default_factory=list)


async def _user(s, email: str, name: str) -> User:
    u = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if u is None:
        u = User(id=uuid.uuid4(), email=email, name=name, password_hash=hash_password(DEMO_PASSWORD))
        s.add(u)
        await s.flush()
    return u


async def _seed_tenant(s, slug: str, name: str, settings: dict) -> tuple[Tenant, bool]:
    t = (await s.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one_or_none()
    if t:
        return t, False
    t = Tenant(id=uuid.uuid4(), slug=slug, name=name, settings=settings)
    s.add(t)
    await s.flush()
    for key, person, role in PEOPLE:
        u = await _user(s, f"{key}@{slug}.test", person)
        s.add(Membership(tenant_id=t.id, user_id=u.id, role=role))
    for kind in ConnectorKind:
        s.add(Connector(tenant_id=t.id, kind=kind, provider="sandbox", name=f"{name} {kind.value}", settings={}))
    for agent_name, role, tools, channels, prompt in AGENTS[slug]:
        s.add(
            Agent(
                tenant_id=t.id,
                name=agent_name,
                role=role,
                allowed_tools=tools,
                channels=channels,
                system_prompt=prompt,
                autonomy=Autonomy.autonomous,
                model="claude-opus-5-5",
            )
        )
    for title, body in DOCS[slug]:
        s.add(SbDocument(tenant_id=t.id, title=title, body=body))
    today = datetime.now(UTC).date()
    for i, (cname, email, phone, company) in enumerate(CONTACTS):
        c = SbContact(
            tenant_id=t.id, name=cname, email=email, phone=phone, company=company, status="customer", source="import"
        )
        s.add(c)
        await s.flush()
        overdue = i % 2 == 0
        s.add(
            SbInvoice(
                tenant_id=t.id,
                contact_id=c.id,
                number=f"INV-{1001 + i}",
                amount_usd=Decimal(900 if i == 0 else 180 + 95 * i),
                status="open",
                due_date=today - timedelta(days=10) if overdue else today + timedelta(days=12),
            )
        )
    for text in WORKFLOW_TEXT[slug]:
        draft = compile_offline(text)
        assert draft.definition and not draft.errors, (text, draft.errors)
        d = draft.definition
        wf = Workflow(id=uuid.uuid4(), tenant_id=t.id, name=d.name, trigger_event=d.trigger.event, enabled=True)
        s.add(wf)
        await s.flush()
        v = WorkflowVersion(
            id=uuid.uuid4(),
            tenant_id=t.id,
            workflow_id=wf.id,
            version=1,
            definition=d.model_dump(mode="json", by_alias=True),
            source_text=text,
        )
        s.add(v)
        await s.flush()
        wf.current_version_id = v.id
    return t, True


async def seed_base() -> SeedSummary:
    summary = SeedSummary()
    async with owner_session() as s:
        for slug, name, settings in [
            (
                "northwind",
                "Northwind HVAC",
                {
                    "timezone": "America/New_York",
                    "hourly_rate_usd": 55,
                    "channel_agents": {"chat": "support", "sms": "support", "voice": "scheduler", "email": "support"},
                    "traffic_events": ["lead.created", "lead.created", "ticket.created"],
                },
            ),
            (
                "brightsmile",
                "Brightsmile Dental",
                {
                    "timezone": "America/Chicago",
                    "hourly_rate_usd": 40,
                    "channel_agents": {
                        "chat": "scheduler",
                        "sms": "scheduler",
                        "voice": "scheduler",
                        "email": "support",
                    },
                    "traffic_events": ["lead.created", "ticket.created"],
                },
            ),
        ]:
            t, created = await _seed_tenant(s, slug, name, settings)
            summary.tenants.append(t)
            if created:
                summary.created.append(slug)
    return summary
