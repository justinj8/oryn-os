"""History backfill: run real workflows for N past days so the dashboard has honest data.

Each event is ingested with a negative time offset (so runs, spans and outcomes are recorded
at their simulated time) and a time scale that shrinks waits and approval timeouts."""

import asyncio
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from temporalio.client import Client

from oryn.core.config import get_settings
from oryn.core.db import owner_session, system_session
from oryn.core.logging import log
from oryn.models import Run, Tenant
from oryn.orchestration.run_workflow import OrynRunWorkflow
from oryn.orchestration.worker import backfill_queue
from oryn.seed.demo_manager import decide_pending, manager_context
from oryn.services.ingest import ingest_event
from oryn.services.traffic import TrafficGenerator

TIME_SCALE = 3600.0  # 1 hour of workflow time = 1 second (a 3-day wait takes 72s)


@dataclass
class BackfillResult:
    runs_started: int
    approvals_decided: int


def _events_for_day(
    day: datetime, n: int, kinds: list[str], gen: TrafficGenerator, rng: random.Random, scheduled: bool = True
):
    out = []
    for _ in range(n):
        at = day.replace(hour=rng.randint(8, 18), minute=rng.randint(0, 59), second=rng.randint(0, 59))
        kind, payload = gen.event(kinds)
        if kind == "ticket.created" and rng.random() < 0.2:
            payload["body"] = f"Please refund ${rng.choice([120, 180, 260, 750])} on INV-{rng.randint(1001, 1006)}"
        out.append((at, kind, payload))
    if scheduled and day.weekday() == 0:
        out.append((day.replace(hour=7, minute=30), "schedule.weekly", {}))
    if scheduled and day.toordinal() % 3 == 0:
        out.append((day.replace(hour=9, minute=5), "invoice.overdue", {}))
    return sorted(out, key=lambda e: e[0])


async def backfill(
    client: Client,
    days: int = 14,
    events_per_day: tuple[int, int] = (6, 14),
    seed: int = 42,
    tenants: list[str] | None = None,
    scheduled: bool = True,
) -> BackfillResult:
    """``scheduled=False`` leaves out the calendar-driven events (weekly report, overdue sweep)."""
    rng = random.Random(seed)
    queue = backfill_queue(get_settings())
    gen = TrafficGenerator(random.Random(seed + 1))
    async with system_session() as s:
        rows = (await s.execute(select(Tenant).order_by(Tenant.slug))).scalars().all()
    selected = [t for t in rows if tenants is None or t.slug in tenants]
    handles, contexts = [], []
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    for t in selected:
        contexts.append(await manager_context(t.id, t.slug))
        kinds = (t.settings or {}).get("traffic_events", ["lead.created", "ticket.created"])
        for back in range(days, 0, -1):
            day = today - timedelta(days=back)
            for at, kind, payload in _events_for_day(day, rng.randint(*events_per_day), kinds, gen, rng, scheduled):
                offset = (at - datetime.now(UTC)).total_seconds()
                r = await ingest_event(
                    client,
                    t.id,
                    kind,
                    "backfill",
                    payload,
                    f"backfill:{uuid.uuid4()}",
                    time_offset_seconds=offset,
                    time_scale=TIME_SCALE,
                    task_queue=queue,
                )
                handles += [
                    client.get_workflow_handle_for(OrynRunWorkflow.run, f"{t.id}:{wid}")
                    for wid in await _workflow_ids(r.run_ids)
                ]
    log.info("backfill.started", runs=len(handles))

    decided = 0
    done = asyncio.Event()

    async def manager() -> None:
        nonlocal decided
        while not done.is_set():
            for ctx in contexts:
                decided += await decide_pending(client, ctx, rng)
            await asyncio.sleep(0.3)

    mgr = asyncio.create_task(manager())
    try:
        results = await asyncio.gather(*(h.result() for h in handles), return_exceptions=True)
        for h, outcome in zip(handles, results, strict=True):
            if isinstance(outcome, BaseException):
                log.warning("backfill.run_failed", workflow_id=h.id, error=f"{type(outcome).__name__}: {outcome}")
    finally:
        done.set()
        await mgr
    return BackfillResult(runs_started=len(handles), approvals_decided=decided)


async def _workflow_ids(run_ids: list[uuid.UUID]) -> list[str]:
    """Temporal ids of the runs an ingest started, minus the tenant prefix."""
    if not run_ids:
        return []
    async with owner_session() as s:
        rows = (await s.execute(select(Run.temporal_workflow_id).where(Run.id.in_(run_ids)))).scalars().all()
    return [r.split(":", 1)[1] for r in rows]
