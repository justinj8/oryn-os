import uuid

from sqlalchemy import select

from oryn.core.db import owner_session
from oryn.models import Approval, Conversation, SbCalendarEvent, SbMessage
from oryn.orchestration.conversation_workflow import UserMessage
from oryn.services.conversations import send_message
from tests.orchestration.wf_helpers import worker


async def _say(env, tenant, text, mid=None, channel="chat", ext="sess-1"):
    return await send_message(
        env.client, tenant.id, channel, ext, UserMessage(text=text, message_id=mid or uuid.uuid4().hex)
    )


async def test_chat_booking_conversation(temporal_env, tenant, acts) -> None:
    async with worker(temporal_env.client, acts):
        r1 = await _say(temporal_env, tenant, "Hi, I'd like to book an appointment")
        assert r1.status == "ok" and "openings" in r1.text
        r2 = await _say(temporal_env, tenant, "the first one works")
        assert r2.status == "ok" and "booked" in r2.text.lower()
    async with owner_session() as s:
        assert len((await s.execute(select(SbCalendarEvent))).scalars().all()) == 1
        msgs = (await s.execute(select(SbMessage.direction).order_by(SbMessage.sent_at))).scalars().all()
        conv = (await s.execute(select(Conversation))).scalar_one()
    assert msgs == ["in", "out", "in", "out"]
    assert conv.channel == "chat" and conv.external_id == "sess-1"


async def test_duplicate_message_id_returns_same_reply(temporal_env, tenant, acts) -> None:
    async with worker(temporal_env.client, acts):
        a = await _say(temporal_env, tenant, "hello", mid="m1")
        b = await _say(temporal_env, tenant, "hello", mid="m1")
    assert a == b
    async with owner_session() as s:
        assert len((await s.execute(select(SbMessage))).scalars().all()) == 2


async def test_refund_request_pending_approval_reply(temporal_env, tenant, acts, invoice) -> None:
    async with worker(temporal_env.client, acts):
        r = await _say(temporal_env, tenant, "I want a refund of $250 for invoice INV-1001")
        assert r.status == "pending_approval" and r.approval_id is not None
        assert "manager" in r.text.lower()
    async with owner_session() as s:
        a = await s.get(Approval, r.approval_id)
    assert a.action_tool == "billing.issue_refund" and a.min_role == "operator"


async def test_large_refund_needs_admin(temporal_env, tenant, acts, invoice) -> None:
    async with owner_session() as s:
        from oryn.models import SbInvoice

        (await s.execute(select(SbInvoice))).scalar_one().amount_usd = 2000
    async with worker(temporal_env.client, acts):
        r = await _say(temporal_env, tenant, "Please refund $750 on INV-1001")
    async with owner_session() as s:
        assert (await s.get(Approval, r.approval_id)).min_role == "admin"
