import asyncio

from oryn.api.routes.events import stream_events
from oryn.core.security import create_access_token
from oryn.core.tenancy import Role
from oryn.observability.bus import LiveEvent, get_event_bus
from tests.factories import make_member, make_tenant


class _Req:
    async def is_disconnected(self) -> bool:
        return False


async def test_sse_streams_tenant_events() -> None:
    t = await make_tenant("acme")
    gen = stream_events(get_event_bus(), t.id, _Req())
    first = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0.2)
    await get_event_bus().publish(LiveEvent(type="run.updated", tenant_id=t.id, run_id=None, data={"n": 1}))
    item = await asyncio.wait_for(first, 5)
    assert item["event"] == "run.updated" and '"n": 1' in item["data"]
    await gen.aclose()


async def test_sse_rejects_foreign_tenant(client) -> None:
    a, b = await make_tenant("alpha"), await make_tenant("beta")
    u = await make_member(a, Role.viewer)
    r = await client.get("/api/events/stream", params={"tenant_id": str(b.id), "token": create_access_token(u.id)})
    assert r.status_code == 403


async def test_sse_rejects_bad_token(client) -> None:
    a = await make_tenant("alpha")
    r = await client.get("/api/events/stream", params={"tenant_id": str(a.id), "token": "nope"})
    assert r.status_code == 401
