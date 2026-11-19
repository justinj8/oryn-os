"""ConversationWorkflow — one long-lived workflow per customer conversation (chat, SMS, voice, email, API).

Each customer message arrives as a Temporal **Update**: the caller (a webhook or the chat API)
gets the agent's reply synchronously, while the conversation's state — which specialist is
talking, pending approvals, transcript — stays durable in Temporal. Duplicate deliveries
(same ``message_id``) return the original reply instead of running the agent twice.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from temporalio import workflow
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from oryn.agents.state import ActionOutcome, AgentStepInput, AgentStepOutput
    from oryn.models import AgentRole, MemoryScope, RunStatus
    from oryn.orchestration.activities import OrynActivities
    from oryn.orchestration.approval_loop import ApprovalLoopCtx, run_approval_loop
    from oryn.orchestration.models import (
        ApprovalDecisionSignal,
        ChannelMessageInput,
        ExecuteActionInput,
        FinalizeInput,
        MarkRunInput,
        OutcomeInput,
    )
    from oryn.orchestration.retry import (
        ACTION_RETRY,
        ACTION_START_TO_CLOSE,
        AGENT_RETRY,
        AGENT_START_TO_CLOSE,
        HEARTBEAT,
        QUICK_RETRY,
        QUICK_START_TO_CLOSE,
    )
    from oryn.policies.approval import WorkflowPolicies
    from oryn.policies.escalation import EscalationPolicy

IDLE_TIMEOUT = timedelta(minutes=30)
MAX_TURNS_PER_RUN = 50
# Every SEGMENT_TURNS turns the agent starts a fresh thread seeded with a short recap, so prompts stay
# bounded without editing past messages (which would invalidate preserved thinking blocks).
SEGMENT_TURNS = 15
RECAP_EXCHANGES = 6
HOLD_MESSAGE = "Thanks — I've asked a manager to approve that, and I'll follow up here as soon as they do."


class ConversationInput(BaseModel):
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    run_id: uuid.UUID
    channel: Literal["chat", "sms", "voice", "email", "api"]
    agent_role: AgentRole
    contact: dict[str, Any] = {}
    address: str | None = None  # where follow-ups go (phone / email)
    blackboard: dict[str, Any] = {}
    replies: dict[str, "AgentReply"] = {}
    turns: int = 0
    segment: int = 0
    recent: list[list[str]] = []  # last few [customer, agent] exchanges, for the recap


class UserMessage(BaseModel):
    text: str
    message_id: str


class AgentReply(BaseModel):
    text: str
    status: Literal["ok", "pending_approval", "escalated", "ended"]
    approval_id: uuid.UUID | None = None


ConversationInput.model_rebuild()


@workflow.defn(name="ConversationWorkflow")
class ConversationWorkflow:
    # workflow.init gives the constructor the input, so state exists before *any* handler runs.
    # Without it, a first message delivered in the same task as the start reaches send() before run().
    @workflow.init
    def __init__(self, inp: ConversationInput) -> None:
        self.inp: ConversationInput | None = inp
        self.role = inp.agent_role
        self.blackboard: dict[str, Any] = dict(inp.blackboard)
        self.replies: dict[str, AgentReply] = dict(inp.replies)
        self.turns = inp.turns
        self.segment = inp.segment
        self.segment_turns = 0
        self.recent: list[list[str]] = [list(x) for x in inp.recent]
        self.lock = asyncio.Lock()
        self.last_activity: datetime = datetime.min.replace(tzinfo=UTC)
        self.pending_approvals: list = []
        self.decisions: dict[Any, ApprovalDecisionSignal] = {}
        self.background: list[asyncio.Task] = []
        self.closed = False

    # ------------------------------------------------------------------ handlers
    @workflow.signal
    def decide_approval(self, sig: ApprovalDecisionSignal) -> None:
        if sig.approval_id not in self.decisions:  # record every decision by id, once
            self.decisions[sig.approval_id] = sig

    @workflow.signal
    def close(self) -> None:
        self.closed = True

    @workflow.query
    def state(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "turns": self.turns,
            "pending_approval_ids": [str(a) for a in self.pending_approvals],
            "blackboard": self.blackboard,
        }

    @workflow.update
    async def send(self, msg: UserMessage) -> AgentReply:
        async with self.lock:  # one turn at a time, in arrival order
            if msg.message_id in self.replies:
                return self.replies[msg.message_id]
            self.last_activity = workflow.now()
            reply = await self._turn(msg)
            self.replies[msg.message_id] = reply
            self.turns += 1
            self.recent = [*self.recent, [msg.text, reply.text]][-RECAP_EXCHANGES:]
            self.segment_turns += 1
            if self.segment_turns >= SEGMENT_TURNS:
                self.segment, self.segment_turns = self.segment + 1, 0
            self.last_activity = workflow.now()
            return reply

    @send.validator
    def _validate(self, msg: UserMessage) -> None:
        if not msg.text.strip():
            raise ValueError("message text is empty")
        if self.closed:
            raise ValueError("conversation is closed")

    # ------------------------------------------------------------------ helpers
    @property
    def _base(self) -> dict[str, Any]:
        assert self.inp
        return {"tenant_id": self.inp.tenant_id, "run_id": self.inp.run_id}

    async def _quick(self, fn, arg) -> Any:
        return await workflow.execute_activity_method(
            fn, arg, start_to_close_timeout=QUICK_START_TO_CLOSE, retry_policy=QUICK_RETRY
        )

    async def _log(self, direction: str, body: str, mid: str, deliver: bool = False) -> None:
        assert self.inp
        await self._quick(
            OrynActivities.channel_message,
            ChannelMessageInput(
                **self._base,
                conversation_id=self.inp.conversation_id,
                channel=self.inp.channel,
                direction=direction,
                body=body,
                address=self.inp.address,
                message_id=mid,
                deliver=deliver,
            ),
        )

    def _thread_key(self) -> str:
        return f"conv-{self.role.value}" if self.segment == 0 else f"conv-{self.role.value}-{self.segment}"

    def _goal(self) -> str:
        assert self.inp
        goal = f"Help the customer over {self.inp.channel}. Keep replies short."
        if self.segment and self.recent:
            recap = "\n".join(f"Customer: {c}\nYou: {a}" for c, a in self.recent)
            goal += f"\n\nThe conversation so far (most recent exchanges):\n{recap}"
        return goal

    def _subjects(self) -> list[tuple[MemoryScope, str]]:
        assert self.inp
        keys = []
        for k in ("email", "phone"):
            if v := self.inp.contact.get(k):
                keys.append((MemoryScope.contact, f"contact:{str(v).lower()}"))
        return keys

    async def _agent(self, text: str | None, resume: ActionOutcome | None = None) -> AgentStepOutput:
        assert self.inp
        return await workflow.execute_activity_method(
            OrynActivities.run_agent_step,
            AgentStepInput(
                tenant_id=self.inp.tenant_id,
                run_id=self.inp.run_id,
                step_key=self._thread_key(),
                agent_role=self.role,
                goal=self._goal(),
                blackboard=self.blackboard,
                trigger={**self.inp.contact, "channel": self.inp.channel},
                subject_keys=self._subjects(),
                policies=WorkflowPolicies(),
                inbound_message=text,
                resume_with=resume,
                conversation_id=self.inp.conversation_id,
                channel=self.inp.channel,
            ),
            start_to_close_timeout=AGENT_START_TO_CLOSE,
            heartbeat_timeout=HEARTBEAT,
            retry_policy=AGENT_RETRY,
        )

    async def _settle(self, out: AgentStepOutput, text: str | None, depth: int = 0) -> AgentReply:
        """Turn an agent step result into a customer reply (following handoffs)."""
        self.blackboard.update(out.blackboard_updates)
        if out.status == "handoff" and out.handoff and depth < 2:
            self.role = out.handoff.role
            self.blackboard.update(out.handoff.context)
            return await self._settle(await self._agent(text), text, depth + 1)
        if out.status == "finished":
            if out.outcome:
                await self._quick(
                    OrynActivities.record_outcome,
                    OutcomeInput(
                        **self._base,
                        type=out.outcome,
                        value_usd=out.outcome_value_usd or 0,
                        key=f"{self._base['run_id']}:{self._thread_key()}:{self.turns}:{out.outcome.value}",
                    ),
                )
            return AgentReply(text=out.reply_text or out.summary, status="ok")
        if out.status == "pending_action" and out.pending_action:
            requested: dict[str, Any] = {}
            task = asyncio.create_task(self._await_approval(out, requested))
            self.background.append(task)
            await workflow.wait_condition(lambda: "id" in requested or task.done())
            return AgentReply(text=HOLD_MESSAGE, status="pending_approval", approval_id=requested.get("id"))
        if out.status == "escalated":
            return AgentReply(
                text="Let me connect you with someone from our team — they'll reply here shortly.", status="escalated"
            )
        return AgentReply(
            text="Sorry, something went wrong on our side. A team member will follow up.", status="escalated"
        )

    def _add_pending(self, approval_id: Any, requested: dict[str, Any]) -> None:
        self.pending_approvals.append(approval_id)
        requested.setdefault("id", approval_id)  # lets the holding reply name the approval

    def _remove_pending(self, approval_id: Any) -> None:
        if approval_id in self.pending_approvals:
            self.pending_approvals.remove(approval_id)

    async def _await_approval(self, out: AgentStepOutput, requested: dict[str, Any]) -> None:
        """Runs in the background after we've told the customer we're checking with a manager."""
        assert self.inp and out.pending_action
        p = out.pending_action
        ctx = ApprovalLoopCtx(
            tenant_id=self.inp.tenant_id,
            run_id=self.inp.run_id,
            time_offset_seconds=0,
            time_scale=1.0,
            escalation=EscalationPolicy(),
            decision=lambda aid: self.decisions.get(aid),
            add_pending=lambda aid: self._add_pending(aid, requested),
            remove_pending=self._remove_pending,
            cancelled=lambda: self.closed,
        )
        result = await run_approval_loop(
            ctx,
            step_id=self._thread_key(),
            tool=p.tool,
            args=p.args,
            idempotency_key=p.idempotency_key,
            description=_describe(p.tool, p.args),
            reasons=p.requirement.reasons,
            min_role=p.requirement.min_role,
            agent_id=p.agent_id,
        )
        async with self.lock:
            if result.approved:
                try:
                    res = await workflow.execute_activity_method(
                        OrynActivities.execute_action,
                        ExecuteActionInput(
                            **self._base,
                            agent_id=p.agent_id,
                            tool=p.tool,
                            args=p.args,
                            idempotency_key=p.idempotency_key,
                        ),
                        start_to_close_timeout=ACTION_START_TO_CLOSE,
                        retry_policy=ACTION_RETRY,
                    )
                    outcome = ActionOutcome(approved=True, result=res, tool_call_id=p.tool_call_id)
                except ActivityError as e:
                    outcome = ActionOutcome(
                        approved=True, result={"error": str(e.cause or e)}, tool_call_id=p.tool_call_id
                    )
            else:
                outcome = ActionOutcome(approved=False, comment=result.comment, tool_call_id=p.tool_call_id)
            follow = await self._settle(await self._agent(None, resume=outcome), None)
            await self._log("out", follow.text, f"followup-{result.approval_id}", deliver=True)

    # ------------------------------------------------------------------ main
    @workflow.run
    async def run(self, inp: ConversationInput) -> str:
        self.last_activity = workflow.now()
        await self._quick(
            OrynActivities.mark_run,
            MarkRunInput(**self._base, status=RunStatus.running, current_step=self.role.value, reopen=True),
        )
        while not self.closed:
            try:
                await workflow.wait_condition(
                    lambda: self.closed or (self.turns >= MAX_TURNS_PER_RUN and not self.pending_approvals),
                    timeout=IDLE_TIMEOUT,
                )
            except TimeoutError:
                if (
                    workflow.now() - self.last_activity >= IDLE_TIMEOUT
                    and not self.pending_approvals
                    and not self.lock.locked()
                ):
                    break
                continue
            if self.turns >= MAX_TURNS_PER_RUN:
                await workflow.wait_condition(workflow.all_handlers_finished)
                recent = dict(list(self.replies.items())[-20:])
                workflow.continue_as_new(
                    inp.model_copy(
                        update={
                            "agent_role": self.role,
                            "blackboard": self.blackboard,
                            "replies": recent,
                            "turns": 0,
                            "segment": self.segment + 1,
                            "recent": self.recent,
                        }
                    )
                )
        await workflow.wait_condition(workflow.all_handlers_finished)
        for t in self.background:
            if not t.done():
                t.cancel()
        await self._quick(
            OrynActivities.finalize_run,
            FinalizeInput(
                **self._base,
                status=RunStatus.completed,
                summary=f"Conversation ended after {self.turns} turns.",
                blackboard=self.blackboard,
            ),
        )
        return "ended"

    async def _record_turn(self, msg: UserMessage, reply: AgentReply) -> None:
        await self._log("in", msg.text, msg.message_id)
        # Email replies are actually sent; SMS/voice/chat replies go back in the HTTP response.
        assert self.inp
        await self._log("out", reply.text, msg.message_id, deliver=self.inp.channel == "email")

    async def _turn(self, msg: UserMessage) -> AgentReply:
        out = await self._agent(msg.text)
        reply = await self._settle(out, msg.text)
        await self._record_turn(msg, reply)
        return reply


def _describe(tool: str, args: dict[str, Any]) -> str:
    if tool == "billing.issue_refund":
        return f"Refund ${float(args.get('amount_usd', 0)):,.2f}"
    if tool == "crm.apply_discount":
        return f"Apply a {args.get('discount_pct')}% discount"
    return tool
