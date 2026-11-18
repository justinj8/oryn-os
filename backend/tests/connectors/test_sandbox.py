import random
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from oryn.connectors.base import ContactIn, DealIn
from oryn.connectors.errors import NonRetryableConnectorError, RetryableConnectorError
from oryn.connectors.faults import FaultInjector
from oryn.connectors.sandbox.billing import SandboxBilling
from oryn.connectors.sandbox.calendar import SandboxCalendar
from oryn.connectors.sandbox.crm import SandboxCRM
from oryn.connectors.sandbox.database import SandboxDatabase
from oryn.connectors.sandbox.docs import SandboxDocs
from oryn.connectors.sandbox.messaging import SandboxMessaging
from oryn.models import SbCalendarEvent, SbDocument, SbMessage
from tests.connectors.conftest import FIXED_NOW


def _cal(session, tenant, faults):
    return SandboxCalendar(session, tenant.id, faults, tz="America/New_York", now=lambda: FIXED_NOW)


async def test_book_is_idempotent(session, tenant, no_faults) -> None:
    cal = _cal(session, tenant, no_faults)
    slot = (await cal.find_slots(30, 5, "any"))[0]
    b1 = await cal.book(slot, "Consult", None, idempotency_key="k1")
    b2 = await cal.book(slot, "Consult", None, idempotency_key="k1")
    assert b1.id == b2.id
    assert (await session.execute(select(func.count()).select_from(SbCalendarEvent))).scalar_one() == 1


async def test_find_slots_business_hours_and_skips_booked(session, tenant, no_faults) -> None:
    cal = _cal(session, tenant, no_faults)
    slots = await cal.find_slots(30, 5, "any")
    assert slots, "expected availability"
    for s in slots:
        local = s.starts_at.astimezone(cal.tz)
        assert local.weekday() < 5 and 9 <= local.hour < 17
        assert s.starts_at > FIXED_NOW
    await cal.book(slots[0], "Consult", None, idempotency_key="k1")
    again = await cal.find_slots(30, 5, "any")
    assert slots[0].starts_at not in {s.starts_at for s in again}


async def test_find_slots_prefers_afternoon(session, tenant, no_faults) -> None:
    slots = await _cal(session, tenant, no_faults).find_slots(30, 5, "afternoon")
    assert slots[0].starts_at.astimezone(slots[0].starts_at.tzinfo).hour >= 17  # 12:00 ET == 17:00 UTC


def test_fault_injector_rate_one_always_raises() -> None:
    import asyncio

    f = FaultInjector(1.0, 0, random.Random(1))
    with pytest.raises(RetryableConnectorError, match="injected"):
        asyncio.run(f.maybe_fail("op"))


async def test_fault_injector_rate_zero_never_raises() -> None:
    f = FaultInjector(0.0, 0, random.Random(1))
    for _ in range(50):
        await f.maybe_fail("op")


async def test_crm_upsert_find_and_deal(session, tenant, no_faults) -> None:
    crm = SandboxCRM(session, tenant.id, no_faults)
    c = await crm.upsert_contact(ContactIn(name="Dana Reyes", email="dana@example.com", phone="+15550101"))
    assert (await crm.find_contact(email="dana@example.com")).id == c.id
    again = await crm.upsert_contact(ContactIn(name="Dana R.", email="dana@example.com"))
    assert again.id == c.id and again.name == "Dana R."
    deal = await crm.create_deal(DealIn(contact_id=c.id, title="Heat pump", amount_usd=8200), idempotency_key="d1")
    same = await crm.create_deal(DealIn(contact_id=c.id, title="Heat pump", amount_usd=8200), idempotency_key="d1")
    assert deal.id == same.id
    disc = await crm.apply_discount(deal.id, 15, idempotency_key="disc1")
    assert disc.discount_pct == Decimal(15)
    assert [d.id for d in await crm.list_deals(c.id)] == [deal.id]


async def test_refund_cannot_exceed_invoice(session, tenant, no_faults) -> None:
    crm = SandboxCRM(session, tenant.id, no_faults)
    c = await crm.upsert_contact(ContactIn(name="Ann", email="ann@example.com"))
    billing = SandboxBilling(session, tenant.id, no_faults, today=FIXED_NOW.date)
    inv = await billing.create_invoice(c.id, 300, idempotency_key="i1")
    refunded = await billing.issue_refund(inv.id, 200, idempotency_key="r1")
    assert refunded.refunded_usd == Decimal(200)
    with pytest.raises(NonRetryableConnectorError):
        await billing.issue_refund(inv.id, 200, idempotency_key="r2")


async def test_messaging_send_is_idempotent(session, tenant, no_faults) -> None:
    m = SandboxMessaging(session, tenant.id, no_faults, now=lambda: FIXED_NOW)
    await m.send_email("a@example.com", "Hi", "Body", idempotency_key="e1")
    await m.send_email("a@example.com", "Hi", "Body", idempotency_key="e1")
    await m.send_sms("+15550101", "Hello", idempotency_key="s1")
    rows = (await session.execute(select(SbMessage.channel))).scalars().all()
    assert sorted(rows) == ["email", "sms"]


async def test_database_query_reads_and_rejects_writes(session, tenant, no_faults) -> None:
    db = SandboxDatabase(session, tenant.id, no_faults)
    res = await db.query("select count(*) as n from sb_contacts", {})
    assert res.columns == ["n"] and res.rows == [[0]]
    for bad in (
        "delete from sb_contacts",
        "select 1; drop table sb_contacts",
        "update sb_deals set stage='x'",
        "with d as (delete from sb_contacts returning *) select * from d",
    ):
        with pytest.raises(NonRetryableConnectorError):
            await db.query(bad, {})


async def test_docs_search_ranks_by_overlap(session, tenant, no_faults) -> None:
    session.add_all(
        [
            SbDocument(tenant_id=tenant.id, title="Refund policy", body="Refunds within 30 days of service."),
            SbDocument(tenant_id=tenant.id, title="Maintenance plan", body="Annual furnace tune-up included."),
        ]
    )
    await session.flush()
    hits = await SandboxDocs(session, tenant.id, no_faults).search("what is your refund policy", k=2)
    assert hits[0].title == "Refund policy"


async def test_build_connector_set_applies_tenant_fault_settings(session, tenant) -> None:
    from oryn.connectors.registry import build_connector_set
    from oryn.core.config import Settings
    from oryn.models import Connector, ConnectorKind

    session.add(
        Connector(
            tenant_id=tenant.id,
            kind=ConnectorKind.calendar,
            provider="sandbox",
            name="Cal",
            settings={"failure_rate": 1.0},
        )
    )
    await session.flush()
    cs = await build_connector_set(session, tenant.id, Settings())
    assert cs.crm.provider == "sandbox"
    with pytest.raises(RetryableConnectorError):
        await cs.calendar.find_slots(30, 5, "any")
    await cs.crm.list_deals()  # crm has no fault override → succeeds
