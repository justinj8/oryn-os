"""Prompts shown in the builder UI. Each is guaranteed to compile offline (tested)."""

EXAMPLES = [
    "When a new lead arrives, have the sales agent qualify the lead and propose a quote. If the lead is qualified, "
    "have the scheduling agent book a 30-minute consultation within 5 business days, otherwise send them a nurture "
    "email. Ask a manager before offering discounts over 10%.",
    "When a new ticket comes in, have the support agent resolve the customer's issue. Ask a manager before issuing "
    "refunds over $250.",
    "When an invoice is overdue, have the ops agent send a payment reminder by text. Wait 3 days, then text them a "
    "payment reminder.",
    "Every Monday, have the reporting agent send the weekly KPI report to the owner.",
    "When a new message is received, have the scheduling agent book a cleaning appointment. Wait 1 day, then send "
    "them an appointment reminder.",
    "When a new lead arrives, if the budget is over $10,000, get an owner's approval, otherwise have the sales agent "
    "qualify the lead and propose a quote.",
]
