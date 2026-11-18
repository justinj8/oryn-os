"""Golden NL → DSL examples. These are also served to the UI as examples that compile offline."""

DEFAULT_APPROVAL = {
    "discount_pct_over": 10.0,
    "refund_usd_over": 200.0,
    "admin_refund_usd_over": 500.0,
    "owner_amount_usd_over": 5000.0,
}
DEFAULT_ESCALATION = {"timeout_seconds": 3600, "ladder": ["operator", "admin", "owner"]}


def _policies(**approval) -> dict:
    return {"approval": {**DEFAULT_APPROVAL, **approval}, "escalation": DEFAULT_ESCALATION}


GOLDENS = [
    (
        "When a new lead arrives, have the sales agent qualify the lead and propose a quote. If the lead is "
        "qualified, have the scheduling agent book a 30-minute consultation within 5 business days, otherwise "
        "send them a nurture email. Ask a manager before offering discounts over 10%.",
        {
            "name": "New lead workflow",
            "trigger": {"event": "lead.created", "filter": {}},
            "steps": [
                {
                    "id": "sales",
                    "next": None,
                    "type": "agent",
                    "role": "sales",
                    "goal": "Qualify the lead and propose a quote",
                },
                {
                    "id": "check_qualified",
                    "next": None,
                    "type": "condition",
                    "if": "blackboard.qualified == true",
                    "then": "scheduler",
                    "else": "notify_email",
                },
                {
                    "id": "scheduler",
                    "next": "end",
                    "type": "agent",
                    "role": "scheduler",
                    "goal": "Book a 30-minute consultation within 5 business days",
                },
                {
                    "id": "notify_email",
                    "next": "end",
                    "type": "notify",
                    "channel": "email",
                    "template": "nurture",
                    "to": None,
                },
            ],
            "policies": _policies(discount_pct_over=10.0),
        },
    ),
    (
        "When a new ticket comes in, have the support agent resolve the customer's issue. "
        "Ask a manager before issuing refunds over $250.",
        {
            "name": "New ticket workflow",
            "trigger": {"event": "ticket.created", "filter": {}},
            "steps": [
                {
                    "id": "support",
                    "next": None,
                    "type": "agent",
                    "role": "support",
                    "goal": "Resolve the customer's issue",
                }
            ],
            "policies": _policies(refund_usd_over=250.0),
        },
    ),
    (
        "When an invoice is overdue, have the ops agent send a payment reminder by text. "
        "Wait 3 days, then text them a payment reminder.",
        {
            "name": "Overdue invoice workflow",
            "trigger": {"event": "invoice.overdue", "filter": {}},
            "steps": [
                {"id": "ops", "next": None, "type": "agent", "role": "ops", "goal": "Send a payment reminder by text"},
                {"id": "wait", "next": None, "type": "wait", "seconds": 259200},
                {
                    "id": "notify_sms",
                    "next": None,
                    "type": "notify",
                    "channel": "sms",
                    "template": "payment_reminder",
                    "to": None,
                },
            ],
            "policies": _policies(),
        },
    ),
    (
        "Every Monday, have the reporting agent send the weekly KPI report to the owner.",
        {
            "name": "Weekly schedule workflow",
            "trigger": {"event": "schedule.weekly", "filter": {}},
            "steps": [
                {
                    "id": "reporting",
                    "next": None,
                    "type": "agent",
                    "role": "reporting",
                    "goal": "Send the weekly KPI report to the owner",
                }
            ],
            "policies": _policies(),
        },
    ),
    (
        "When a new message is received, have the scheduling agent book a cleaning appointment. "
        "Wait 1 day, then send them an appointment reminder.",
        {
            "name": "New message workflow",
            "trigger": {"event": "message.received", "filter": {}},
            "steps": [
                {
                    "id": "scheduler",
                    "next": None,
                    "type": "agent",
                    "role": "scheduler",
                    "goal": "Book a cleaning appointment",
                },
                {"id": "wait", "next": None, "type": "wait", "seconds": 86400},
                {
                    "id": "notify_email",
                    "next": None,
                    "type": "notify",
                    "channel": "email",
                    "template": "appointment_reminder",
                    "to": None,
                },
            ],
            "policies": _policies(),
        },
    ),
]
