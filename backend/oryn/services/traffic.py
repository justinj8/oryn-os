"""Live traffic simulator: generates realistic inbound events for tenants that switch it on.

Runs as a small asyncio loop inside the worker process. Events go through the normal
``ingest_event`` path, so every simulated lead is a real workflow run."""

import asyncio
import json
import random
import uuid
from typing import Any

from sqlalchemy import select
from temporalio.client import Client

from oryn.core.db import system_session
from oryn.core.logging import log
from oryn.models import Tenant
from oryn.observability.bus import get_event_bus

FIRST = [
    "Dana",
    "Lee",
    "Priya",
    "Marcus",
    "Sofia",
    "Ethan",
    "Aisha",
    "Noah",
    "Grace",
    "Mateo",
    "Chloe",
    "Omar",
    "Hannah",
    "Diego",
    "Mei",
    "Jonah",
    "Lucia",
    "Kwame",
    "Ava",
    "Ravi",
]
LAST = [
    "Reyes",
    "Chen",
    "Patel",
    "Johnson",
    "Garcia",
    "Okafor",
    "Kim",
    "Novak",
    "Silva",
    "Brooks",
    "Haddad",
    "Larsen",
    "Nguyen",
    "Moreau",
    "Adeyemi",
    "Rossi",
]
COMPANIES = [
    "Maple Dental",
    "Brightline Logistics",
    "Summit Realty",
    "Harbor Cafe",
    "Pioneer Builders",
    "Northstar Fitness",
    "Cedar Law",
    "Bluebird Bakery",
    None,
    None,
]
NEEDS = [
    "heat pump install",
    "furnace replacement",
    "AC tune-up",
    "duct cleaning",
    "smart thermostat",
    "new patient cleaning",
    "teeth whitening",
    "invisalign consult",
    "emergency repair",
]
ISSUES = [
    "My furnace is making a weird noise",
    "What is your refund policy?",
    "Do you have weekend hours?",
    "My AC stopped working",
    "I have a tooth pain since yesterday",
    "Is the maintenance plan worth it?",
]


def flag_key(tenant_id: uuid.UUID) -> str:
    return f"oryn:{tenant_id}:traffic"


class TrafficGenerator:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def event(self, kinds: list[str]) -> tuple[str, dict[str, Any]]:
        r = self.rng
        first, last = r.choice(FIRST), r.choice(LAST)
        email = f"{first.lower()}.{last.lower()}{r.randint(1, 999)}@example.com"
        kind = r.choice(kinds)
        if kind == "ticket.created":
            return kind, {"name": f"{first} {last}", "email": email, "subject": "Help needed", "body": r.choice(ISSUES)}
        budget = r.choice([400, 1200, 2500, 4200, 6800, 8200, 12500, 18000])
        payload: dict[str, Any] = {
            "name": f"{first} {last}",
            "email": email,
            "phone": f"+1555{r.randint(1000000, 9999999)}",
            "company": r.choice(COMPANIES),
            "need": r.choice(NEEDS),
            "budget_usd": budget,
            "source": r.choice(["web", "web", "phone", "referral"]),
        }
        if budget >= 6000 and r.random() < 0.45:
            payload["requested_discount_pct"] = r.choice([5, 10, 15, 20])
        if r.random() < 0.3:
            payload["preferred_time"] = r.choice(["morning", "afternoon"])
        return kind, payload


async def get_flag(tenant_id: uuid.UUID) -> dict[str, Any]:
    raw = await get_event_bus().redis.get(flag_key(tenant_id))
    return json.loads(raw) if raw else {"enabled": False, "rate_per_min": 4}


async def set_flag(tenant_id: uuid.UUID, enabled: bool, rate_per_min: int) -> dict[str, Any]:
    value = {"enabled": enabled, "rate_per_min": rate_per_min}
    await get_event_bus().redis.set(flag_key(tenant_id), json.dumps(value))
    return value


async def traffic_loop(client: Client, tick_s: float = 5.0) -> None:
    from oryn.services.ingest import ingest_event

    gen = TrafficGenerator()
    credit: dict[uuid.UUID, float] = {}
    while True:
        try:
            async with system_session() as s:
                tenants = (await s.execute(select(Tenant))).scalars().all()
            for t in tenants:
                flag = await get_flag(t.id)
                if not flag.get("enabled"):
                    continue
                credit[t.id] = credit.get(t.id, 0.0) + flag["rate_per_min"] * tick_s / 60
                kinds = (t.settings or {}).get("traffic_events", ["lead.created", "ticket.created"])
                while credit[t.id] >= 1:
                    credit[t.id] -= 1
                    kind, payload = gen.event(kinds)
                    await ingest_event(client, t.id, kind, "simulator", payload, f"traffic:{uuid.uuid4()}")
        except Exception as e:  # the demo generator must never take the worker down
            log.warning("traffic.tick_failed", error=str(e))
        await asyncio.sleep(tick_s)
