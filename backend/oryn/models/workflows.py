import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from oryn.core.tenancy import Role
from oryn.models.base import Base, TenantScoped, str_enum
from oryn.models.enums import ApprovalStatus, OutcomeType, RunStatus, SpanKind


class Workflow(Base, TenantScoped):
    __tablename__ = "workflows"
    name: Mapped[str] = mapped_column(String(200))
    trigger_event: Mapped[str] = mapped_column(String(64), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    current_version_id: Mapped[uuid.UUID | None]


class WorkflowVersion(Base, TenantScoped):
    __tablename__ = "workflow_versions"
    __table_args__ = (UniqueConstraint("workflow_id", "version"),)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict[str, Any]]
    source_text: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Event(Base, TenantScoped):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    type: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Run(Base, TenantScoped):
    __tablename__ = "runs"
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflows.id", ondelete="SET NULL"))
    workflow_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16), default="workflow")
    title: Mapped[str] = mapped_column(String(300), default="")
    temporal_workflow_id: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[RunStatus] = mapped_column(str_enum(RunStatus), default=RunStatus.running, index=True)
    trigger_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    started_by_user_id: Mapped[uuid.UUID | None]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))
    simulated_cost: Mapped[bool] = mapped_column(Boolean, default=True)
    outcome_summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    blackboard: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Span(Base, TenantScoped):
    __tablename__ = "spans"
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    parent_span_id: Mapped[uuid.UUID | None]
    agent_id: Mapped[uuid.UUID | None]
    kind: Mapped[SpanKind] = mapped_column(str_enum(SpanKind))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="running")
    input: Mapped[dict[str, Any] | None]
    output: Mapped[dict[str, Any] | None]
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Approval(Base, TenantScoped):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str] = mapped_column(String(100))
    action_tool: Mapped[str | None] = mapped_column(String(64))
    action_args: Mapped[dict[str, Any]] = mapped_column(default=dict)
    description: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str] = mapped_column(String(255))
    risk_reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    min_role: Mapped[Role] = mapped_column(str_enum(Role))
    status: Mapped[ApprovalStatus] = mapped_column(
        str_enum(ApprovalStatus), default=ApprovalStatus.pending, index=True
    )
    requested_by_agent_id: Mapped[uuid.UUID | None]
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None]
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)


class AgentThread(Base, TenantScoped):
    __tablename__ = "agent_threads"
    __table_args__ = (UniqueConstraint("run_id", "step_key"),)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    step_key: Mapped[str] = mapped_column(String(100))
    messages: Mapped[list[Any]] = mapped_column(default=list)
    iterations: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))


class Outcome(Base, TenantScoped):
    __tablename__ = "outcomes"
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    type: Mapped[OutcomeType] = mapped_column(str_enum(OutcomeType))
    value_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal(0))
    minutes_saved: Mapped[int] = mapped_column(Integer, default=0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Conversation(Base, TenantScoped):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("tenant_id", "channel", "external_id"),)
    channel: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(200))
    contact_id: Mapped[uuid.UUID | None]
    run_id: Mapped[uuid.UUID | None]
    temporal_workflow_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="open")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
