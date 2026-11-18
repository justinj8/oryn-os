from enum import StrEnum


class ConnectorKind(StrEnum):
    crm = "crm"
    email = "email"
    sms = "sms"
    voice = "voice"
    calendar = "calendar"
    billing = "billing"
    database = "database"
    docs = "docs"
    chat = "chat"


class AgentRole(StrEnum):
    sales = "sales"
    support = "support"
    scheduler = "scheduler"
    reporting = "reporting"
    ops = "ops"


class Autonomy(StrEnum):
    suggest = "suggest"
    act_with_approval = "act_with_approval"
    autonomous = "autonomous"


class RunStatus(StrEnum):
    running = "running"
    waiting_approval = "waiting_approval"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    escalated = "escalated"


class SpanKind(StrEnum):
    run = "run"
    agent = "agent"
    llm_call = "llm_call"
    tool_call = "tool_call"
    handoff = "handoff"
    approval = "approval"
    decision = "decision"
    retry = "retry"
    error = "error"
    notify = "notify"
    wait = "wait"


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    cancelled = "cancelled"


class MemoryScope(StrEnum):
    contact = "contact"
    account = "account"
    agent = "agent"
    tenant = "tenant"


class OutcomeType(StrEnum):
    meeting_booked = "meeting_booked"
    deal_created = "deal_created"
    ticket_resolved = "ticket_resolved"
    invoice_collected = "invoice_collected"
    report_delivered = "report_delivered"
    lead_nurtured = "lead_nurtured"
