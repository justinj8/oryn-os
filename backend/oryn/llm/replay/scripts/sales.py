from oryn.llm.replay.state import ReplayMove, ReplayState, move

QUALIFY_BUDGET_USD = 3000


def next_move(st: ReplayState) -> ReplayMove:
    t = st.trigger
    email, phone, name = t.get("email"), t.get("phone"), t.get("name", "there")
    budget = float(t.get("budget_usd") or 0)
    need = t.get("need") or "general inquiry"

    if (f := st.failed_last()) is not None:  # one retry after a transient tool error
        return move(f.name, **f.call.arguments)

    if not st.done("crm.find_contact"):
        return move("crm.find_contact", email=email, phone=phone)

    contact = (st.last("crm.find_contact").result or {}).get("contact")
    if not contact:
        up = st.last("crm.upsert_contact")
        if not up:
            return move(
                "crm.upsert_contact",
                name=name,
                email=email,
                phone=phone,
                company=t.get("company"),
                source=t.get("source"),
                attributes={"need": need, "budget_usd": budget},
            )
        contact = (up.result or {}).get("contact") or {}

    qualified = budget >= QUALIFY_BUDGET_USD
    if not st.done("control.update_blackboard"):
        return move(
            "control.update_blackboard",
            facts={
                "qualified": qualified,
                "budget_usd": budget,
                "need": need,
                "contact_id": contact.get("id"),
                "contact_email": email,
                "contact_name": name,
                "contact_phone": phone,
            },
        )

    deal = None
    if qualified:
        created = st.last("crm.create_deal")
        if not created:
            title = f"{need.title()} — {t.get('company') or name}"
            return move("crm.create_deal", contact_id=contact.get("id"), title=title, amount_usd=budget)
        deal = (created.result or {}).get("deal") or {}
        pct = t.get("requested_discount_pct")
        if pct and not st.done("crm.apply_discount"):
            return move("crm.apply_discount", deal_id=deal.get("id"), discount_pct=float(pct))

    if not st.done("control.remember") and email:
        fact = f"Interested in {need}; budget about ${budget:,.0f}."
        if t.get("preferred_time"):
            fact += f" Prefers {t['preferred_time']} appointments."
        return move("control.remember", scope="contact", subject_key=f"contact:{email.lower()}", fact=fact)

    if qualified:
        return move(
            "control.handoff",
            role="scheduler",
            goal="Book a 30-minute consultation within 5 business days and confirm by email.",
            context={
                "deal_id": (deal or {}).get("id"),
                "deal_amount_usd": budget,
                "prefer": t.get("preferred_time") or "any",
            },
        )
    return move(
        "control.finish",
        summary=f"Lead {name} not yet qualified (budget ${budget:,.0f}); added to nurture.",
        outcome="lead_nurtured",
    )
