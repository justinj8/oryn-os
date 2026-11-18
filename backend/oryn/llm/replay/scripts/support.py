import re

from oryn.llm.replay.intents import Intent, classify
from oryn.llm.replay.state import ReplayMove, ReplayState, move

GREETINGS = ["Hi! How can I help you today?", "Hello! What can I do for you?"]


def _refund_details(text: str, trigger: dict) -> tuple[str | None, float | None]:
    number = trigger.get("invoice_number")
    m = re.search(r"\bINV-\d+\b", text, re.IGNORECASE)
    if m:
        number = m.group(0).upper()
    amount = trigger.get("amount_usd")
    a = re.search(r"\$\s?([\d,]+(?:\.\d{1,2})?)", text)
    if a:
        amount = float(a.group(1).replace(",", ""))
    return number, (float(amount) if amount is not None else None)


def next_move(st: ReplayState) -> ReplayMove:
    if (f := st.failed_last()) is not None and f.name not in ("billing.issue_refund",):
        return move(f.name, **f.call.arguments)
    text = (
        st.last_user()
        if st.ctx.step_key.startswith("conv")
        else (st.trigger.get("body") or st.trigger.get("text") or st.last_user())
    )
    intent = classify(text)

    if intent is Intent.refund:
        return _refund(st, text)
    if intent in (Intent.book_appointment, Intent.reschedule, Intent.select_slot):
        return move("control.handoff", role="scheduler", goal="Help the customer book an appointment.", context={})
    if intent is Intent.greeting:
        return move("control.finish", summary="Greeted customer.", reply=st.pick(GREETINGS))
    if intent is Intent.goodbye:
        return move(
            "control.finish",
            summary="Conversation closed.",
            reply="You're welcome — have a great day!",
            outcome="ticket_resolved",
        )
    if intent is Intent.unknown:
        unknowns = sum(1 for t in st.user_texts() if classify(t) is Intent.unknown)
        if unknowns >= 2:
            return move("control.escalate_to_human", reason="Could not understand the customer's request twice.")
        return move(
            "control.finish",
            summary="Asked for clarification.",
            reply="Sorry, I didn't quite catch that. Could you tell me a bit more about what you need?",
        )

    # pricing / billing / support: answer from the knowledge base
    if not st.done("docs.search"):
        return move("docs.search", query=text, k=2)
    hits = (st.last("docs.search").result or {}).get("hits") or []
    if not hits:
        return move("control.escalate_to_human", reason="No knowledge-base article matched the question.")
    top = hits[0]
    return move(
        "control.finish",
        summary=f"Answered from '{top['title']}'.",
        reply=f"{top['snippet']} (from our {top['title'].lower()})",
        outcome="ticket_resolved",
    )


def _refund(st: ReplayState, text: str) -> ReplayMove:
    number, amount = _refund_details(text, st.trigger)
    if not number or not amount:
        return move(
            "control.finish",
            summary="Asked for refund details.",
            reply="I can help with that. Which invoice (e.g. INV-1001) and how much should be refunded?",
        )
    if not st.done("db.query"):
        return move(
            "db.query",
            sql="select id, amount_usd, refunded_usd from sb_invoices where number = :n",
            params={"n": number},
        )
    rows = (st.last("db.query").result or {}).get("rows") or []
    if not rows:
        return move(
            "control.finish",
            summary=f"Invoice {number} not found.",
            reply=f"I couldn't find invoice {number}. Could you double-check the number?",
        )
    refund = st.last("billing.issue_refund")
    if refund is None:
        return move("billing.issue_refund", invoice_id=rows[0][0], amount_usd=amount)
    res = refund.result or {}
    if res.get("approved") is False:
        return move(
            "control.finish",
            summary=f"Refund of ${amount:,.2f} declined by a manager.",
            reply=f"A manager reviewed your refund request and couldn't approve it"
            f"{': ' + res['comment'] if res.get('comment') else '.'}",
            outcome="ticket_resolved",
        )
    if "error" in res:
        return move("control.escalate_to_human", reason=f"Refund failed: {res['error']}")
    return move(
        "control.finish",
        summary=f"Refunded ${amount:,.2f} on {number}.",
        reply=f"Your refund of ${amount:,.2f} for {number} has been processed.",
        outcome="ticket_resolved",
    )
