import json
import uuid

from oryn.llm.replay.intents import Intent, classify
from oryn.llm.replay.provider import ReplayProvider
from oryn.llm.types import ChatMessage, ReplayContext
from oryn.tools.registry import default_registry

CID, DID = str(uuid.uuid4()), str(uuid.uuid4())
LEAD = {
    "name": "Dana Reyes",
    "email": "dana@example.com",
    "phone": "+15550101",
    "company": "Reyes Dental",
    "need": "heat pump install",
    "budget_usd": 8200,
    "requested_discount_pct": 15,
    "source": "web",
}

FAKE_RESULTS = {
    "crm.find_contact": {"found": False, "contact": None},
    "crm.upsert_contact": {"contact": {"id": CID, "name": "Dana Reyes", "email": "dana@example.com"}},
    "crm.create_deal": {"deal": {"id": DID, "amount_usd": "8200.00"}},
    "crm.apply_discount": {"deal": {"id": DID, "discount_pct": "15"}},
    "calendar.find_slots": {"slots": [{"starts_at": "2026-11-17T14:00:00Z", "ends_at": "2026-11-17T14:30:00Z"}]},
    "calendar.book": {"id": str(uuid.uuid4()), "starts_at": "2026-11-17T14:00:00Z"},
}


async def drive(
    role: str,
    trigger: dict,
    first_user: str = "Handle this lead.",
    results=FAKE_RESULTS,
    max_steps: int = 12,
    blackboard: dict | None = None,
) -> list[str]:
    p = ReplayProvider(seed=7)
    specs = default_registry().all_specs()
    msgs = [ChatMessage(role="user", content=first_user)]
    names: list[str] = []
    ctx = ReplayContext(agent_role=role, step_key="s1", trigger=trigger, blackboard=blackboard or {})
    for _ in range(max_steps):
        r = await p.complete(model="m", system="sys", messages=msgs, tools=specs, context=ctx)
        assert len(r.tool_calls) == 1
        call = r.tool_calls[0]
        names.append(call.name)
        if call.name in ("control.handoff", "control.finish", "control.escalate_to_human"):
            return names
        msgs.append(ChatMessage(role="assistant", tool_calls=[call]))
        msgs.append(
            ChatMessage(role="tool", tool_call_id=call.id, content=json.dumps(results.get(call.name, {"ok": True})))
        )
    return names


async def test_replay_is_deterministic() -> None:
    p = ReplayProvider(seed=7)
    ctx = ReplayContext(agent_role="sales", step_key="s1", trigger=LEAD)
    args = dict(
        model="m",
        system="s",
        messages=[ChatMessage(role="user", content="go")],
        tools=default_registry().all_specs(),
        context=ctx,
    )
    assert (await p.complete(**args)) == (await p.complete(**args))


async def test_sales_golden_sequence() -> None:
    assert await drive("sales", LEAD) == [
        "crm.find_contact",
        "crm.upsert_contact",
        "control.update_blackboard",
        "crm.create_deal",
        "crm.apply_discount",
        "control.remember",
        "control.handoff",
    ]


async def test_unqualified_lead_finishes_nurtured() -> None:
    names = await drive("sales", {**LEAD, "budget_usd": 400, "requested_discount_pct": None})
    assert names[-1] == "control.finish"
    assert "crm.create_deal" not in names


async def test_scheduler_books_and_confirms() -> None:
    bb = {"contact_id": CID, "contact_email": "dana@example.com", "contact_name": "Dana Reyes", "deal_amount_usd": 8200}
    assert await drive("scheduler", LEAD, blackboard=bb) == [
        "calendar.find_slots",
        "calendar.book",
        "messaging.send_email",
        "control.finish",
    ]


async def test_support_unknown_twice_escalates() -> None:
    p = ReplayProvider()
    specs = default_registry().all_specs()
    ctx = ReplayContext(agent_role="support", step_key="conv", trigger={})
    msgs = [ChatMessage(role="user", content="blorp zzzt")]
    r1 = await p.complete(model="m", system="s", messages=msgs, tools=specs, context=ctx)
    assert r1.tool_calls[0].name == "control.finish"
    msgs += [
        ChatMessage(role="assistant", tool_calls=r1.tool_calls),
        ChatMessage(role="tool", tool_call_id=r1.tool_calls[0].id, content="{}"),
        ChatMessage(role="user", content="qwfp arst"),
    ]
    r2 = await p.complete(model="m", system="s", messages=msgs, tools=specs, context=ctx)
    assert r2.tool_calls[0].name == "control.escalate_to_human"


async def test_repeated_tool_error_escalates() -> None:
    errs = {**FAKE_RESULTS, "crm.find_contact": {"error": "boom", "class": "retryable"}}
    names = await drive("sales", LEAD, results=errs)
    assert names == ["crm.find_contact", "crm.find_contact", "control.escalate_to_human"]


async def test_usage_nonzero_and_simulated() -> None:
    r = await ReplayProvider().complete(
        model="claude-opus-5-5",
        system="You are a sales agent.",
        messages=[ChatMessage(role="user", content="go")],
        tools=default_registry().all_specs(),
        context=ReplayContext(agent_role="sales", step_key="s", trigger=LEAD),
    )
    assert r.simulated and r.usage.input_tokens > 0 and r.usage.output_tokens > 0
    assert r.model == "claude-opus-5-5"


def test_intents() -> None:
    assert classify("Can I book an appointment for Tuesday?") is Intent.book_appointment
    assert classify("I want a refund for invoice INV-1001") is Intent.refund
    assert classify("how much does a heat pump cost?") is Intent.pricing
    assert classify("hello there") is Intent.greeting
    assert classify("my furnace is making a weird noise") is Intent.support_issue
    assert classify("xyzzy") is Intent.unknown
