from oryn.llm.replay.state import ReplayMove, ReplayState, move

MAX_REMINDERS = 3


def next_move(st: ReplayState) -> ReplayMove:
    if (f := st.failed_last()) is not None:
        return move(f.name, **f.call.arguments)
    if not st.done("billing.list_overdue"):
        return move("billing.list_overdue")
    invoices = ((st.last("billing.list_overdue").result or {}).get("invoices") or [])[:MAX_REMINDERS]
    looked = [c for c in st.turn_calls if c.name == "crm.get_contact"]
    sent = [c for c in st.turn_calls if c.name == "messaging.send_sms"]
    if len(looked) < len(invoices):
        return move("crm.get_contact", contact_id=invoices[len(looked)]["contact_id"])
    if len(sent) < len(invoices):
        inv = invoices[len(sent)]
        contact = (looked[len(sent)].result or {}).get("contact") or {}
        if contact.get("phone"):
            first = (contact.get("name") or "there").split()[0]
            return move(
                "messaging.send_sms",
                to=contact["phone"],
                body=f"Hi {first}, a friendly reminder that invoice {inv['number']} for "
                f"${float(inv['amount_usd']):,.2f} is past due. Reply PAY for a payment link.",
            )
    total = sum(float(i["amount_usd"]) for i in invoices)
    return move("control.finish", summary=f"Sent {len(sent)} payment reminders covering ${total:,.2f} overdue.")
