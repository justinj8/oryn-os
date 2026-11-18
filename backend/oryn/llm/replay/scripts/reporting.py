from oryn.llm.replay.state import ReplayMove, ReplayState, move

KPI_SQL = """
select
  (select count(*) from sb_contacts where created_at > now() - interval '7 days') as new_leads,
  (select count(*) from sb_deals where created_at > now() - interval '7 days') as new_deals,
  (select coalesce(sum(amount_usd), 0) from sb_deals where created_at > now() - interval '7 days') as pipeline_usd,
  (select count(*) from sb_calendar_events where status = 'confirmed'
     and created_at > now() - interval '7 days') as meetings_booked,
  (select count(*) from sb_invoices where status = 'open' and due_date < current_date) as overdue_invoices
"""


def next_move(st: ReplayState) -> ReplayMove:
    if (f := st.failed_last()) is not None:
        return move(f.name, **f.call.arguments)
    if not st.done("db.query"):
        return move("db.query", sql=KPI_SQL.strip(), params={})
    res = st.last("db.query").result or {}
    row = dict(zip(res.get("columns", []), (res.get("rows") or [[]])[0], strict=False))
    lines = [
        f"- {k.replace('_', ' ')}: {v:,.0f}" if isinstance(v, int | float) else f"- {k}: {v}" for k, v in row.items()
    ]
    to = st.trigger.get("recipient") or st.bb.get("report_recipient") or "owner@example.com"
    if not st.done("messaging.send_email"):
        return move(
            "messaging.send_email",
            to=to,
            subject="Your weekly operations report",
            body="Here is this week's summary:\n" + "\n".join(lines),
        )
    return move(
        "control.finish",
        summary="Weekly report delivered: " + "; ".join(lines).replace("- ", ""),
        outcome="report_delivered",
    )
