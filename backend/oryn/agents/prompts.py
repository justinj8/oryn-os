import json
from typing import Any

from oryn.models import Agent, Memory

BASE_SYSTEM = """You are {name}, the {role} agent of {tenant} on Oryn OS.
Work only through the provided tools. Be concise and factual.
- Share facts other agents need with control.update_blackboard.
- Save durable facts about customers with control.remember.
- When another specialist should continue, use control.handoff with a clear goal.
- When your task is complete, call control.finish with a short summary (and a customer-facing reply
  if you are talking to a customer). Report a business outcome when one happened.
- If you cannot proceed safely, call control.escalate_to_human.
Some actions require human approval; if an action is declined, continue without it."""


def system_prompt(agent: Agent, tenant_name: str) -> str:
    base = BASE_SYSTEM.format(name=agent.name, role=agent.role.value, tenant=tenant_name)
    return f"{base}\n\n{agent.system_prompt}".strip()


def task_message(goal: str, trigger: dict[str, Any], blackboard: dict[str, Any], memories: list[Memory]) -> str:
    parts = [f"Goal: {goal}"]
    if trigger:
        parts.append("Trigger event:\n" + json.dumps(trigger, default=str, indent=2))
    if blackboard:
        parts.append("Shared run facts (blackboard):\n" + json.dumps(blackboard, default=str, indent=2))
    if memories:
        parts.append("What we remember:\n" + "\n".join(f"- {m.content}" for m in memories))
    return "\n\n".join(parts)
