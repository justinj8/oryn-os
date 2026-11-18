"""Runs one agent step: load the thread, run the graph, persist the thread, return the result."""

import json
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oryn.agents.graph import MAX_AGENT_ITERATIONS, build_agent_graph, initial_state
from oryn.agents.prompts import system_prompt, task_message
from oryn.agents.state import (
    ActionOutcome,
    AgentStepInput,
    AgentStepOutput,
    ExecutedAction,
    Handoff,
    PendingAction,
    StepScope,
)
from oryn.connectors.registry import ConnectorSet
from oryn.core.config import Settings
from oryn.llm.types import ChatMessage, LLMProvider, Usage
from oryn.memory.store import MemoryStore
from oryn.models import Agent, AgentThread, MemoryScope, SpanKind, Tenant
from oryn.observability.sink import SpanSink
from oryn.tools.registry import ToolRegistry

__all__ = [
    "MAX_AGENT_ITERATIONS",
    "ActionOutcome",
    "AgentDeps",
    "AgentStepInput",
    "AgentStepOutput",
    "ExecutedAction",
    "Handoff",
    "PendingAction",
    "run_agent",
]


@dataclass
class AgentDeps:
    llm: LLMProvider
    registry: ToolRegistry
    memory: MemoryStore
    spans: SpanSink
    session: AsyncSession
    connectors: ConnectorSet
    settings: Settings


async def _load_agent(s: AsyncSession, inp: AgentStepInput) -> Agent | None:
    if inp.agent_id:
        return await s.get(Agent, inp.agent_id)
    q = select(Agent).where(Agent.role == inp.agent_role, Agent.enabled.is_(True)).order_by(Agent.name).limit(1)
    return (await s.execute(q)).scalar_one_or_none()


async def run_agent(inp: AgentStepInput, deps: AgentDeps) -> AgentStepOutput:
    s = deps.session
    agent = await _load_agent(s, inp)
    if agent is None:
        return AgentStepOutput(status="failed", summary=f"no enabled {inp.agent_role.value} agent is configured")

    thread = (
        await s.execute(
            select(AgentThread).where(AgentThread.run_id == inp.run_id, AgentThread.step_key == inp.step_key)
        )
    ).scalar_one_or_none()
    if thread is None:
        tenant = await s.get(Tenant, inp.tenant_id)
        subjects = [*inp.subject_keys, (MemoryScope.agent, f"agent:{agent.role.value}")]
        memories = await deps.memory.recall(s, subjects, inp.goal + " " + (inp.inbound_message or ""))
        messages = [ChatMessage(role="user", content=task_message(inp.goal, inp.trigger, inp.blackboard, memories))]
        thread = AgentThread(
            tenant_id=inp.tenant_id,
            run_id=inp.run_id,
            step_key=inp.step_key,
            messages=[],
            iterations=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=Decimal(0),
        )
        s.add(thread)
        tenant_name = tenant.name if tenant else "the business"
    else:
        messages = [ChatMessage.model_validate(m) for m in thread.messages]
        tenant_name = ""
    if inp.resume_with:
        r = inp.resume_with
        payload = (
            {"approved": True, **(r.result or {})}
            if r.approved
            else {"approved": False, "declined": True, "comment": r.comment or "declined by a human reviewer"}
        )
        messages.append(ChatMessage(role="tool", tool_call_id=r.tool_call_id, content=json.dumps(payload, default=str)))
    if inp.inbound_message:
        messages.append(ChatMessage(role="user", content=inp.inbound_message))

    agent_span = await deps.spans.start(
        SpanKind.agent,
        f"{agent.name} · {inp.step_key}",
        {"goal": inp.goal, "resume": inp.resume_with is not None, "inbound": inp.inbound_message},
        None,
        agent.id,
    )
    scope = StepScope(
        inp=inp,
        agent_id=agent.id,
        model=agent.model or deps.settings.default_model,
        system=system_prompt(agent, tenant_name or "the business"),
        max_tokens=agent.max_tokens_per_run,
        max_cost=Decimal(agent.max_cost_usd_per_run),
        agent_span=agent_span,
    )
    graph = build_agent_graph(deps, agent, scope)
    prior_usage = Usage(input_tokens=thread.input_tokens, output_tokens=thread.output_tokens)
    try:
        final = await graph.ainvoke(
            initial_state(messages, thread.iterations, prior_usage, Decimal(thread.cost_usd)),
            {"recursion_limit": 4 * MAX_AGENT_ITERATIONS + 4},
        )
    except Exception as e:
        await deps.spans.end(agent_span, {"error": str(e)}, status="error")
        raise

    thread.messages = [m.model_dump(mode="json") for m in final["messages"]]
    step_usage = Usage(
        input_tokens=final["usage"].input_tokens - prior_usage.input_tokens,
        output_tokens=final["usage"].output_tokens - prior_usage.output_tokens,
    )
    step_cost = final["cost"] - Decimal(thread.cost_usd)
    thread.iterations = final["iterations"]
    thread.input_tokens, thread.output_tokens = final["usage"].input_tokens, final["usage"].output_tokens
    thread.cost_usd = final["cost"]
    await s.flush()

    out = AgentStepOutput(
        status=final["status"] or "finished",
        summary=final["summary"],
        reply_text=final.get("reply"),
        blackboard_updates=final["blackboard_updates"],
        executed_actions=final["executed"],
        handoff=final.get("handoff"),
        pending_action=final.get("pending"),
        outcome=final.get("outcome"),
        outcome_value_usd=final.get("outcome_value"),
        usage=step_usage,
        cost_usd=step_cost,
        iterations=final["iterations"],
        agent_id=agent.id,
    )
    await deps.spans.end(
        agent_span,
        {"status": out.status, "summary": out.summary},
        status="error" if out.status in ("failed", "escalated") else "ok",
    )
    return out
