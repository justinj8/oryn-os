"""The workflow DSL: a validated JSON document that the Temporal workflow interprets."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from oryn.core.tenancy import Role
from oryn.models import AgentRole
from oryn.policies.approval import WorkflowPolicies
from oryn.policies.escalation import EscalationPolicy
from oryn.workflows.conditions import ConditionSyntaxError, parse

END = "end"


class _Step(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(pattern=r"^[a-z0-9_\-]{1,40}$")
    next: str | None = None


class AgentStep(_Step):
    type: Literal["agent"] = "agent"
    role: AgentRole
    goal: str


class ConditionStep(_Step):
    type: Literal["condition"] = "condition"
    if_: str = Field(alias="if")
    then: str
    else_: str = Field(alias="else")


class ApprovalStep(_Step):
    type: Literal["approval"] = "approval"
    description: str
    min_role: Role = Role.operator


class WaitStep(_Step):
    type: Literal["wait"] = "wait"
    seconds: int = Field(ge=1, le=60 * 60 * 24 * 30)


class NotifyStep(_Step):
    type: Literal["notify"] = "notify"
    channel: Literal["email", "sms"]
    template: str
    to: str | None = None


class ParallelStep(_Step):
    type: Literal["parallel"] = "parallel"
    branches: list[AgentStep] = Field(min_length=2, max_length=5)


Step = Annotated[
    AgentStep | ConditionStep | ApprovalStep | WaitStep | NotifyStep | ParallelStep, Field(discriminator="type")
]


class Trigger(BaseModel):
    event: str
    filter: dict[str, str | int | float | bool] = {}


class PolicySet(BaseModel):
    approval: WorkflowPolicies = WorkflowPolicies()
    escalation: EscalationPolicy = EscalationPolicy()


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    trigger: Trigger
    steps: list[Step]
    policies: PolicySet = PolicySet()

    def step(self, step_id: str) -> Step:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(step_id)

    def next_of(self, step_id: str) -> str:
        """The explicit ``next`` or the following step; the last step defaults to end."""
        s = self.step(step_id)
        if s.next:
            return s.next
        ids = [x.id for x in self.steps]
        i = ids.index(step_id)
        return ids[i + 1] if i + 1 < len(ids) else END

    @property
    def first(self) -> str:
        return self.steps[0].id if self.steps else END


def _targets(d: WorkflowDefinition, s: Step) -> list[str]:
    if isinstance(s, ConditionStep):
        return [s.then, s.else_]
    return [d.next_of(s.id)]


def validate_definition(d: WorkflowDefinition) -> list[str]:
    errors: list[str] = []
    if not d.steps:
        return ["workflow has no steps"]
    seen: set[str] = set()
    for s in d.steps:
        if s.id in seen:
            errors.append(f"duplicate step id '{s.id}'")
        seen.add(s.id)
    if errors:
        return errors
    for s in d.steps:
        if isinstance(s, ConditionStep):
            try:
                parse(s.if_)
            except ConditionSyntaxError as e:
                errors.append(f"step '{s.id}' has an invalid condition: {e}")
        errors += [f"step '{s.id}' points to unknown step '{t}'" for t in _targets(d, s) if t != END and t not in seen]
    if errors:
        return errors
    # cycle detection (workflows are DAGs; loops belong in agents, not in the graph)
    state: dict[str, int] = {}

    def visit(node: str, path: list[str]) -> str | None:
        if node == END:
            return None
        if state.get(node) == 1:
            return " → ".join([*path, node])
        if state.get(node) == 2:
            return None
        state[node] = 1
        for t in _targets(d, d.step(node)):
            if cyc := visit(t, [*path, node]):
                return cyc
        state[node] = 2
        return None

    for s in d.steps:
        if cyc := visit(s.id, []):
            errors.append(f"workflow contains a cycle: {cyc}")
            break
    return errors
