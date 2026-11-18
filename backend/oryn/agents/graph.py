"""The agent loop as a LangGraph state machine.

    think ──(tool calls)──▶ act ──▶ think ...
      │                      │
      └──(status set)──▶ END ◀┘

The important design decision lives in ``act``: before any side-effecting tool runs, the
approval policy is evaluated. If a human must approve, the loop *stops* and returns a
``PendingAction`` to the Temporal workflow instead of executing it. The workflow waits
durably (minutes or days, surviving restarts), then executes the action in a separate,
idempotent activity and resumes this same thread with the outcome.
"""

import json
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from langgraph.graph import END, START, StateGraph

from oryn.agents.state import (
    ExecutedAction,
    GraphState,
    Handoff,
    PendingAction,
    Requirement,
    StepScope,
)
from oryn.connectors.errors import classify_error
from oryn.llm.pricing import cost_usd
from oryn.llm.types import ChatMessage, ReplayContext, ToolCall
from oryn.models import Agent, MemoryScope, OutcomeType, SpanKind
from oryn.policies.approval import ProposedAction, evaluate_approval
from oryn.tools.registry import ToolArgsError, ToolContext

if TYPE_CHECKING:
    from oryn.agents.runner import AgentDeps

MAX_AGENT_ITERATIONS = 8


def _tool_msg(call: ToolCall, payload: dict[str, Any]) -> ChatMessage:
    return ChatMessage(role="tool", tool_call_id=call.id, content=json.dumps(payload, default=str))


def build_agent_graph(deps: "AgentDeps", agent: Agent, scope: StepScope):
    inp = scope.inp
    specs = deps.registry.specs_for(agent.allowed_tools)
    allowed = {s.name for s in specs}

    async def think(state: GraphState) -> GraphState:
        if state["iterations"] >= MAX_AGENT_ITERATIONS:
            return {
                "status": "escalated",
                "summary": f"Stopped after {MAX_AGENT_ITERATIONS} iterations without finishing.",
            }
        total = state["usage"].input_tokens + state["usage"].output_tokens
        if total > scope.max_tokens or state["cost"] > scope.max_cost:
            return {
                "status": "escalated",
                "summary": f"Stopped: per-run budget exceeded ({total} tokens, ${state['cost']:.4f}).",
            }
        span = await deps.spans.start(
            SpanKind.llm_call, scope.model, {"messages": len(state["messages"])}, scope.agent_span, scope.agent_id
        )
        try:
            res = await deps.llm.complete(
                model=scope.model,
                system=scope.system,
                messages=state["messages"],
                tools=specs,
                context=ReplayContext(
                    agent_role=inp.agent_role.value,
                    step_key=inp.step_key,
                    trigger=inp.trigger,
                    blackboard={**inp.blackboard, **state["blackboard_updates"]},
                ),
            )
        except Exception as e:
            await deps.spans.end(span, {"error": str(e)}, status="error")
            raise
        cost = cost_usd(res.model, res.usage)
        await deps.spans.end(
            span,
            {"text": res.text, "tool_calls": [c.model_dump() for c in res.tool_calls], "stop_reason": res.stop_reason},
            usage=res.usage,
            cost=cost,
            simulated=res.simulated,
        )
        update: GraphState = {
            "messages": [
                *state["messages"],
                ChatMessage(role="assistant", content=res.text, tool_calls=res.tool_calls, raw=res.raw),
            ],
            "iterations": state["iterations"] + 1,
            "usage": state["usage"] + res.usage,
            "cost": state["cost"] + cost,
            "queued_calls": res.tool_calls,
        }
        if res.stop_reason == "refusal":
            update |= {"status": "escalated", "summary": "The model declined this request."}
        elif not res.tool_calls:
            update |= {"status": "finished", "summary": res.text or "Done.", "reply": res.text or None}
        return update

    async def act(state: GraphState) -> GraphState:
        messages = list(state["messages"])
        bb = dict(state["blackboard_updates"])
        executed = list(state["executed"])
        out: GraphState = {}
        calls = list(state["queued_calls"])
        for i, call in enumerate(calls):
            if out.get("status"):  # an earlier call ended the step; answer the rest so history stays valid
                messages.append(_tool_msg(call, {"skipped": True}))
                continue
            name, args = call.name, call.arguments
            if name not in allowed:
                messages.append(
                    _tool_msg(
                        call, {"error": f"tool '{name}' is not available to this agent", "class": "non_retryable"}
                    )
                )
                continue
            if name == "control.update_blackboard":
                bb.update(args.get("facts") or {})
                messages.append(_tool_msg(call, {"ok": True}))
            elif name == "control.remember":
                await deps.memory.remember(
                    deps.session,
                    inp.tenant_id,
                    MemoryScope(args.get("scope", "contact")),
                    str(args.get("subject_key")),
                    str(args.get("fact")),
                    inp.run_id,
                )
                messages.append(_tool_msg(call, {"ok": True}))
            elif name == "control.finish":
                out |= {
                    "status": "finished",
                    "summary": args.get("summary") or "Done.",
                    "reply": args.get("reply"),
                    "outcome": OutcomeType(args["outcome"]) if args.get("outcome") else None,
                    "outcome_value": args.get("outcome_value_usd"),
                }
                messages.append(_tool_msg(call, {"ok": True}))
            elif name == "control.handoff":
                h = Handoff.model_validate(args)
                bb.update(h.context)
                out |= {"status": "handoff", "handoff": h, "summary": f"Handed off to {h.role.value}: {h.goal}"}
                messages.append(_tool_msg(call, {"ok": True}))
            elif name == "control.escalate_to_human":
                out |= {"status": "escalated", "summary": f"Escalated: {args.get('reason', '')}"}
                messages.append(_tool_msg(call, {"ok": True}))
            else:
                result = await _business_tool(call, i)
                if isinstance(result, PendingAction):
                    out |= {"status": "pending_action", "pending": result, "summary": f"Waiting for approval: {name}"}
                    continue  # its tool_result is appended when the decision comes back
                payload, executed_action = result
                if executed_action:
                    executed.append(executed_action)
                messages.append(_tool_msg(call, payload))
        return out | {"messages": messages, "blackboard_updates": bb, "executed": executed, "queued_calls": []}

    async def _business_tool(call: ToolCall, index: int):
        spec = deps.registry.get(call.name).spec
        key = f"{inp.run_id}:{inp.step_key}:{call.id}"
        try:
            deps.registry.validate_args(call.name, call.arguments)
        except ToolArgsError as e:
            return {"error": str(e), "class": "non_retryable"}, None
        if spec.side_effect:
            req = evaluate_approval(ProposedAction.from_spec(spec, call.arguments), agent.autonomy, inp.policies)
            if req.required:
                assert req.min_role is not None
                span = await deps.spans.start(
                    SpanKind.decision,
                    f"approval required: {call.name}",
                    {"args": call.arguments},
                    scope.agent_span,
                    scope.agent_id,
                )
                await deps.spans.end(span, {"min_role": req.min_role.value, "reasons": list(req.reasons)})
                return PendingAction(
                    tool=call.name,
                    args=call.arguments,
                    idempotency_key=key,
                    tool_call_id=call.id,
                    requirement=Requirement(min_role=req.min_role, reasons=list(req.reasons)),
                    agent_id=scope.agent_id,
                )
        span = await deps.spans.start(SpanKind.tool_call, call.name, call.arguments, scope.agent_span, scope.agent_id)
        ctx = ToolContext(
            tenant_id=inp.tenant_id,
            run_id=inp.run_id,
            agent_id=scope.agent_id,
            session=deps.session,
            connectors=deps.connectors,
            idempotency_key=key,
        )
        try:
            async with deps.session.begin_nested():  # a failed tool must not poison the step's transaction
                result = await deps.registry.invoke(call.name, ctx, call.arguments)
        except Exception as e:
            cls = classify_error(e)
            await deps.spans.end(span, {"error": str(e), "class": cls.value}, status="error")
            return {"error": str(e), "class": cls.value}, None
        await deps.spans.end(span, result)
        return result, (
            ExecutedAction(tool=call.name, idempotency_key=key, result=result) if spec.side_effect else None
        )

    def route(state: GraphState) -> str:
        return END if state.get("status") else "act"

    def route_after_act(state: GraphState) -> str:
        return END if state.get("status") else "think"

    g = StateGraph(GraphState)
    g.add_node("think", think)
    g.add_node("act", act)
    g.add_edge(START, "think")
    g.add_conditional_edges("think", route, {"act": "act", END: END})
    g.add_conditional_edges("act", route_after_act, {"think": "think", END: END})
    return g.compile()


def initial_state(messages: list[ChatMessage], iterations: int, usage, cost: Decimal) -> GraphState:
    return {
        "messages": messages,
        "queued_calls": [],
        "iterations": iterations,
        "usage": usage,
        "cost": cost,
        "blackboard_updates": {},
        "executed": [],
        "status": None,
        "summary": "",
        "reply": None,
        "handoff": None,
        "pending": None,
        "outcome": None,
        "outcome_value": None,
    }
