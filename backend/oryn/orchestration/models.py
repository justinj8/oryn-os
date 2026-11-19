"""Temporal payloads. Pydantic models, serialized by Temporal's pydantic data converter."""

import uuid
from typing import Any

from pydantic import BaseModel

from oryn.agents.state import ExecutedAction
from oryn.core.tenancy import Role
from oryn.models import ApprovalStatus, OutcomeType, RunStatus
from oryn.workflows.dsl import NotifyStep, WorkflowDefinition


class _TenantRun(BaseModel):
    tenant_id: uuid.UUID
    run_id: uuid.UUID
    time_offset_seconds: float = 0


class RunInput(_TenantRun):
    workflow_version_id: uuid.UUID | None = None
    definition: WorkflowDefinition
    trigger: dict[str, Any] = {}
    trigger_event_id: uuid.UUID | None = None
    started_by_user_id: uuid.UUID | None = None
    time_scale: float = 1.0


class RunResult(BaseModel):
    status: RunStatus
    summary: str
    outcomes: list[OutcomeType] = []


class RunState(BaseModel):
    status: RunStatus
    current_step: str | None
    blackboard: dict[str, Any]
    pending_approval_id: uuid.UUID | None
    steps_done: list[str]


class ApprovalDecisionSignal(BaseModel):
    approval_id: uuid.UUID
    approved: bool
    decided_by: uuid.UUID | None = None
    comment: str | None = None


class MarkRunInput(_TenantRun):
    status: RunStatus
    current_step: str | None = None
    reopen: bool = False  # conversations can be resumed after they ended


class ChannelMessageInput(_TenantRun):
    conversation_id: uuid.UUID
    channel: str
    direction: str  # "in" | "out"
    body: str
    address: str | None = None
    message_id: str
    deliver: bool = False  # out-of-band follow-up: actually send through the channel connector


class RequestApprovalInput(_TenantRun):
    step_id: str
    tool: str | None
    args: dict[str, Any] = {}
    idempotency_key: str
    description: str
    reasons: list[str] = []
    min_role: Role
    expires_in_s: int
    agent_id: uuid.UUID | None = None


class UpdateApprovalInput(_TenantRun):
    approval_id: uuid.UUID
    status: ApprovalStatus
    min_role: Role | None = None
    escalation_level: int | None = None
    expires_in_s: int | None = None
    comment: str | None = None


class ExecuteActionInput(_TenantRun):
    agent_id: uuid.UUID | None
    tool: str
    args: dict[str, Any]
    idempotency_key: str


class NotifyInput(_TenantRun):
    step: NotifyStep
    trigger: dict[str, Any] = {}
    blackboard: dict[str, Any] = {}


class OutcomeInput(_TenantRun):
    type: OutcomeType
    value_usd: float = 0
    key: str | None = None  # idempotency key: a retried activity must not count the outcome twice


class CompensateInput(_TenantRun):
    actions: list[ExecutedAction]


class FinalizeInput(_TenantRun):
    status: RunStatus
    summary: str
    error: str | None = None
    blackboard: dict[str, Any] = {}


class FlagForHumanInput(_TenantRun):
    conversation_id: uuid.UUID
    reason: str


class SpanEventInput(_TenantRun):
    kind: str
    name: str
    data: dict[str, Any] = {}
    status: str = "ok"
