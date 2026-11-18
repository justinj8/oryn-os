"""Control tools: how an agent talks to the orchestrator rather than to the outside world.

Their handlers are no-ops; the agent graph interprets the call itself (finish the step,
hand off, write memory, escalate, or share facts on the run blackboard).
"""

from typing import Any

from pydantic import BaseModel, Field

from oryn.models import AgentRole, MemoryScope, OutcomeType
from oryn.tools.registry import RiskLevel, ToolContext, ToolRegistry, ToolSpec


class HandoffIn(BaseModel):
    role: AgentRole
    goal: str
    context: dict[str, Any] = {}


class FinishIn(BaseModel):
    summary: str
    reply: str | None = Field(None, description="Message to send back to the customer, if any.")
    outcome: OutcomeType | None = None
    outcome_value_usd: float | None = None


class RememberIn(BaseModel):
    scope: MemoryScope = MemoryScope.contact
    subject_key: str
    fact: str


class EscalateIn(BaseModel):
    reason: str


class BlackboardIn(BaseModel):
    facts: dict[str, Any]


async def _noop(ctx: ToolContext, args: Any) -> dict:
    return {"ok": True}


def register_control(reg: ToolRegistry) -> None:
    for name, desc, model in [
        ("control.handoff", "Hand the task to another specialist agent with a clear goal.", HandoffIn),
        ("control.finish", "Finish your task with a summary (and a customer reply if conversational).", FinishIn),
        ("control.remember", "Save a durable fact about a contact/account for future conversations.", RememberIn),
        ("control.escalate_to_human", "Escalate to a human when you cannot proceed safely.", EscalateIn),
        ("control.update_blackboard", "Share structured facts with other agents on this run.", BlackboardIn),
    ]:
        reg.register(ToolSpec(name, desc, model, RiskLevel.low, False, None), _noop)
