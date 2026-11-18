"""Inputs, outputs and graph state for one agent step. All Temporal-serializable (pydantic)."""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, TypedDict

from pydantic import BaseModel

from oryn.core.tenancy import Role
from oryn.llm.types import ChatMessage, ToolCall, Usage
from oryn.models import AgentRole, MemoryScope, OutcomeType
from oryn.policies.approval import WorkflowPolicies


class ActionOutcome(BaseModel):
    """What happened to an action that was held for approval."""

    approved: bool
    tool_call_id: str
    result: dict[str, Any] | None = None
    comment: str | None = None


class Requirement(BaseModel):
    min_role: Role
    reasons: list[str]


class PendingAction(BaseModel):
    tool: str
    args: dict[str, Any]
    idempotency_key: str
    requirement: Requirement
    tool_call_id: str
    agent_id: uuid.UUID | None = None


class Handoff(BaseModel):
    role: AgentRole
    goal: str
    context: dict[str, Any] = {}


class ExecutedAction(BaseModel):
    tool: str
    idempotency_key: str
    result: dict[str, Any]


class AgentStepInput(BaseModel):
    tenant_id: uuid.UUID
    run_id: uuid.UUID
    step_key: str
    agent_role: AgentRole
    agent_id: uuid.UUID | None = None
    goal: str
    blackboard: dict[str, Any] = {}
    trigger: dict[str, Any] = {}
    subject_keys: list[tuple[MemoryScope, str]] = []
    policies: WorkflowPolicies = WorkflowPolicies()
    resume_with: ActionOutcome | None = None
    inbound_message: str | None = None
    conversation_id: uuid.UUID | None = None
    channel: str | None = None
    time_offset_seconds: float = 0


Status = Literal["finished", "handoff", "pending_action", "escalated", "failed"]


class AgentStepOutput(BaseModel):
    status: Status
    summary: str
    reply_text: str | None = None
    blackboard_updates: dict[str, Any] = {}
    executed_actions: list[ExecutedAction] = []
    handoff: Handoff | None = None
    pending_action: PendingAction | None = None
    outcome: OutcomeType | None = None
    outcome_value_usd: float | None = None
    usage: Usage = Usage()
    cost_usd: Decimal = Decimal(0)
    iterations: int = 0
    agent_id: uuid.UUID | None = None


class GraphState(TypedDict, total=False):
    messages: list[ChatMessage]
    queued_calls: list[ToolCall]
    iterations: int
    usage: Usage
    cost: Decimal
    blackboard_updates: dict[str, Any]
    executed: list[ExecutedAction]
    status: Status | None
    summary: str
    reply: str | None
    handoff: Handoff | None
    pending: PendingAction | None
    outcome: OutcomeType | None
    outcome_value: float | None


@dataclass
class StepScope:
    """Per-step constants the graph nodes close over."""

    inp: AgentStepInput
    agent_id: uuid.UUID
    model: str
    system: str
    max_tokens: int
    max_cost: Decimal
    agent_span: uuid.UUID
