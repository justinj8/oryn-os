from datetime import datetime

from oryn.llm.replay.intents import Intent, classify, slot_choice
from oryn.llm.replay.state import ReplayMove, ReplayState, move


def _fmt(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%a %b %d, %H:%M UTC")
    except ValueError:
        return iso


def _prefer(st: ReplayState) -> str:
    text = st.prompt_text().lower()
    if "prefers morning" in text or "morning" in st.last_user().lower():
        return "morning"
    if "prefers afternoon" in text or "afternoon" in st.last_user().lower():
        return "afternoon"
    return str(st.bb.get("prefer") or st.trigger.get("preferred_time") or "any")


def _contact(st: ReplayState) -> tuple[str | None, str | None, str]:
    bb, t = st.bb, st.trigger
    return (
        bb.get("contact_id") or t.get("contact_id"),
        bb.get("contact_email") or t.get("email"),
        bb.get("contact_name") or t.get("name") or "there",
    )


def next_move(st: ReplayState) -> ReplayMove:
    if (f := st.failed_last()) is not None and f.name != "calendar.book":
        return move(f.name, **f.call.arguments)
    conversational = st.ctx.step_key.startswith("conv")
    return _conversation(st) if conversational else _task(st)


def _task(st: ReplayState) -> ReplayMove:
    contact_id, email, name = _contact(st)
    if not st.done("calendar.find_slots"):
        return move("calendar.find_slots", duration_min=30, within_days=5, prefer=_prefer(st))
    slots = st.result("calendar.find_slots").get("slots") or []
    if not slots:
        return move("control.escalate_to_human", reason="No availability in the next 5 business days.")
    booked = st.last("calendar.book")
    if booked is None or (booked.result or {}).get("error"):
        idx = 0 if booked is None else min(1, len(slots) - 1)  # slot taken? try the next one
        s = slots[idx]
        return move(
            "calendar.book",
            starts_at=s["starts_at"],
            ends_at=s["ends_at"],
            title=f"Consultation: {name}",
            contact_id=contact_id,
        )
    when = _fmt((booked.result or {}).get("starts_at", ""))
    if email and not st.done("messaging.send_email"):
        return move(
            "messaging.send_email",
            to=email,
            subject="Your appointment is confirmed",
            body=f"Hi {name.split()[0]}, you're booked for {when}. Reply to this email to reschedule.",
        )
    amount = float(st.bb.get("deal_amount_usd") or 0)
    return move(
        "control.finish",
        summary=f"Booked {name} for {when}.",
        reply=f"You're booked for {when}.",
        outcome="meeting_booked",
        outcome_value_usd=amount,
    )


def _conversation(st: ReplayState) -> ReplayMove:
    contact_id, _email, name = _contact(st)
    text = st.last_user()
    prior_slots = st.last("calendar.find_slots", turn_only=False) or None
    slots = ((prior_slots.result or {}).get("slots") if prior_slots else None) or []
    choice = slot_choice(text) if slots else None
    intent = classify(text)

    if (
        choice is not None
        and choice < len(slots)
        and intent in (Intent.select_slot, Intent.book_appointment, Intent.unknown, Intent.goodbye)
    ):
        booked = st.last("calendar.book")
        if booked is None:
            s = slots[choice]
            return move(
                "calendar.book",
                starts_at=s["starts_at"],
                ends_at=s["ends_at"],
                title=f"Appointment: {name}",
                contact_id=contact_id,
            )
        if "error" in (booked.result or {}):
            return move(
                "control.finish",
                summary="Slot was taken",
                reply="Sorry — that slot was just taken. Want me to look for other times?",
            )
        when = _fmt((booked.result or {}).get("starts_at", ""))
        return move(
            "control.finish",
            summary=f"Booked appointment for {when}.",
            reply=f"Done! You're booked for {when}. See you then.",
            outcome="meeting_booked",
            outcome_value_usd=float(st.bb.get("deal_amount_usd") or 0),
        )

    if not st.done("calendar.find_slots"):
        return move("calendar.find_slots", duration_min=30, within_days=5, prefer=_prefer(st))
    found = st.result("calendar.find_slots").get("slots") or []
    if not found:
        return move("control.escalate_to_human", reason="No availability found.")
    options = "; ".join(f"({i + 1}) {_fmt(s['starts_at'])}" for i, s in enumerate(found[:3]))
    return move(
        "control.finish",
        summary="Offered appointment slots.",
        reply=f"I have these openings: {options}. Which works best?",
    )
