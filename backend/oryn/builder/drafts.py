"""Draft a workflow from natural language: Claude when configured, the offline grammar otherwise."""

import json

from oryn.builder.examples import EXAMPLES
from oryn.builder.grammar import DraftResult, compile_offline
from oryn.core.config import get_settings
from oryn.llm.replay.provider import ReplayProvider
from oryn.llm.types import ChatMessage, LLMProvider
from oryn.workflows.dsl import WorkflowDefinition, validate_definition

SYSTEM = """You turn a business owner's description of an operational workflow into Oryn OS workflow JSON.
Steps run in order unless `next` (or a condition's then/else) says otherwise; use "end" to stop.
Agent roles: sales, support, scheduler, reporting, ops. Notify channels: email, sms.
Condition expressions use paths like blackboard.qualified or trigger.budget_usd with == != > >= < <= and/or.
Only include steps the description asks for. Put approval thresholds in policies.approval."""


async def draft_workflow(text: str, provider: LLMProvider | None = None) -> DraftResult:
    provider = provider or _provider()
    if isinstance(provider, ReplayProvider) or not text.strip():
        return compile_offline(text)
    shots = "\n\n".join(
        f"Description: {ex}\nJSON: {json.dumps(d.model_dump(mode='json', by_alias=True))}"
        for ex in EXAMPLES[:3]
        if (d := compile_offline(ex).definition) is not None
    )
    try:
        res = await provider.complete(
            model=get_settings().default_model,
            system=SYSTEM + "\n\nExamples:\n" + shots,
            messages=[ChatMessage(role="user", content=f"Description: {text}")],
            tools=[],
            response_schema=WorkflowDefinition,
            max_tokens=4096,
        )
        definition = WorkflowDefinition.model_validate_json(res.text)
    except Exception as e:  # never leave the user with nothing: fall back to the deterministic compiler
        fallback = compile_offline(text)
        fallback.warnings.insert(0, f"The AI drafter failed ({type(e).__name__}); used the offline compiler instead.")
        return fallback
    return DraftResult(definition=definition, errors=validate_definition(definition))


def _provider() -> LLMProvider:
    from oryn.llm.factory import get_llm_provider

    return get_llm_provider(get_settings())
