import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from oryn.core.db import owner_session
from oryn.llm.types import Usage
from oryn.models import Run, Span, SpanKind
from oryn.observability.bus import EventBus, LiveEvent, get_event_bus
from oryn.observability.clock import OffsetClock
from oryn.observability.spans import DbSpanSink
from tests.factories import make_tenant


async def _run(t) -> uuid.UUID:
    rid = uuid.uuid4()
    async with owner_session() as s:
        s.add(Run(id=rid, tenant_id=t.id, temporal_workflow_id=f"wf-{rid}", started_at=datetime.now(UTC)))
    return rid


async def test_offset_clock_backdates() -> None:
    c = OffsetClock(-86400)
    assert abs((datetime.now(UTC) - timedelta(days=1) - c.now()).total_seconds()) < 2


async def test_span_sink_writes_and_publishes() -> None:
    t = await make_tenant("acme")
    rid = await _run(t)
    bus = get_event_bus()
    received: list[LiveEvent] = []

    async def listen() -> None:
        async for ev in bus.subscribe(t.id):
            received.append(ev)
            if len(received) == 2:
                return

    task = asyncio.create_task(listen())
    await asyncio.sleep(0.2)
    sink = DbSpanSink(t.id, rid, bus, OffsetClock(0))
    sid = await sink.start(SpanKind.tool_call, "calendar.book", {"x": 1})
    await sink.end(sid, {"ok": True}, usage=Usage(input_tokens=3, output_tokens=4), cost=Decimal("0.01"))
    await asyncio.wait_for(task, 5)
    assert [e.type for e in received] == ["span.started", "span.ended"]
    assert received[0].run_id == rid
    async with owner_session() as s:
        span = (await s.execute(select(Span))).scalar_one()
    assert span.status == "ok" and span.output == {"ok": True} and span.cost_usd == Decimal("0.01")
    assert span.ended_at is not None and span.input_tokens == 3


async def test_bus_isolates_tenants() -> None:
    bus: EventBus = get_event_bus()
    a, b = uuid.uuid4(), uuid.uuid4()
    got: list[LiveEvent] = []

    async def listen() -> None:
        async for ev in bus.subscribe(a):
            got.append(ev)
            return

    task = asyncio.create_task(listen())
    await asyncio.sleep(0.2)
    await bus.publish(LiveEvent(type="run.updated", tenant_id=b, run_id=None, data={"leak": True}))
    await bus.publish(LiveEvent(type="run.updated", tenant_id=a, run_id=None, data={"mine": True}))
    await asyncio.wait_for(task, 5)
    assert got[0].data == {"mine": True}


async def test_span_writes_do_not_need_the_step_pool() -> None:
    """Regression: an agent step holds a pooled connection for its whole transaction, and its
    span writes need their own short transactions. If both came from one pool, N concurrent
    steps could hold every connection while waiting for one more — a pool deadlock."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from oryn.core import db
    from oryn.core.config import get_settings
    from oryn.core.db import tenant_session

    t = await make_tenant("acme")
    rid = await _run(t)
    saved = db._engines.pop("app", None)
    db._engines["app"] = create_async_engine(
        get_settings().database_url_app, pool_size=1, max_overflow=0, pool_timeout=1
    )
    try:
        async with tenant_session(t.id):  # the step's transaction holds the only app connection
            sink = DbSpanSink(t.id, rid, get_event_bus(), OffsetClock(0))
            sid = await asyncio.wait_for(sink.start(SpanKind.tool_call, "x"), 5)
            await sink.end(sid, {"ok": True})
    finally:
        await db._engines.pop("app").dispose()
        if saved:
            db._engines["app"] = saved
