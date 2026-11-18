"""Offline natural-language → workflow compiler.

A small, documented phrase grammar (not an LLM). Every sentence either compiles into a step or
policy, or comes back as a warning — nothing is silently dropped. With ``LLM_PROVIDER=anthropic``
the builder uses Claude instead (``drafts.py``) and validates the result with the same schema.

Supported phrases:
  trigger    When a new lead|ticket|call|email|message arrives/comes in/is received
             When an invoice is overdue · Every Monday|day|week
  agent      have|ask|let the sales|support|scheduling|reporting|ops agent <goal>
  condition  If the lead is (not) qualified, <step>[, otherwise <step>]
             If the customer is a VIP, … · If the budget|amount is over|under $N, …
  policy     Ask a manager|admin|owner before offering discounts over N%
             Ask a manager before issuing refunds over $N
  approval   Get a manager's|admin's|owner's approval [before …]
  wait       Wait N minutes|hours|days|weeks
  notify     Send|email|text them a <template> (nurture email, appointment reminder, payment reminder, …)
"""

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from oryn.workflows.dsl import WorkflowDefinition, validate_definition

EVENT_NAMES = {
    "lead.created": "New lead",
    "ticket.created": "New ticket",
    "invoice.overdue": "Overdue invoice",
    "call.received": "New call",
    "email.received": "New email",
    "message.received": "New message",
    "schedule.weekly": "Weekly schedule",
    "schedule.daily": "Daily schedule",
}
NOUN_EVENTS = {
    "lead": "lead.created",
    "ticket": "ticket.created",
    "invoice": "invoice.overdue",
    "call": "call.received",
    "email": "email.received",
    "message": "message.received",
}
ROLES = {
    "sales": "sales",
    "support": "support",
    "scheduling": "scheduler",
    "scheduler": "scheduler",
    "reporting": "reporting",
    "ops": "ops",
    "operations": "ops",
    "billing": "ops",
}
APPROVER = {"manager": "operator", "admin": "admin", "owner": "owner"}
UNITS = {"minute": 60, "hour": 3600, "day": 86400, "week": 604800}
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

R_TRIGGER = re.compile(
    r"^(?:when|whenever)\s+(?:a\s+|an\s+)?(?:new\s+)?(?P<noun>lead|ticket|invoice|call|email|message)s?\s+"
    r"(?:arrives|comes in|is created|is overdue|becomes overdue|is received|is submitted|is opened)\b"
    r"[,\s]*(?P<rest>.*)$",
    re.I,
)
R_SCHEDULE = re.compile(
    r"^every\s+(?P<period>" + "|".join(WEEKDAYS) + r"|day|morning|weekday|week)\b[,\s]*(?P<rest>.*)$", re.I
)
R_AGENT = re.compile(
    r"^(?:have|ask|let|get)\s+the\s+(?P<role>" + "|".join(ROLES) + r")\s+agent\s+(?:to\s+)?(?P<goal>.+)$", re.I
)
R_IF = re.compile(
    r"^if\s+(?P<cond>.+?),\s*(?:then\s+)?(?P<then>.+?)(?:,?\s*(?:otherwise|else)\s*,?\s*(?P<else>.+))?$", re.I
)
R_DISCOUNT = re.compile(
    r"^ask\s+(?:a|an|the)\s+(?:manager|admin|owner)\s+before\s+(?:offering|giving|applying)\s+"
    r"(?:any\s+)?discounts?\s+(?:over|above|of more than|greater than)\s+(?P<n>\d+(?:\.\d+)?)\s*%$",
    re.I,
)
R_REFUND = re.compile(
    r"^ask\s+(?:a|an|the)\s+(?:manager|admin|owner)\s+before\s+(?:issuing|giving|approving|processing)\s+"
    r"(?:any\s+)?refunds?\s+(?:over|above|of more than|greater than)\s+\$?(?P<n>\d+(?:\.\d+)?)$",
    re.I,
)
R_APPROVAL = re.compile(
    r"^(?:get|require|request)\s+(?:a\s+|an\s+)?(?P<who>manager|admin|owner)(?:'s)?\s+approval"
    r"(?:\s+before\s+(?P<before>.+))?$",
    re.I,
)
R_WAIT = re.compile(r"^wait\s+(?:for\s+)?(?P<n>\d+)\s+(?P<unit>minute|hour|day|week)s?$", re.I)
R_NOTIFY = re.compile(
    r"^(?P<verb>send|email|text)\s+(?:them|the customer|the lead|the contact)?\s*(?:a\s+|an\s+)?"
    r"(?P<what>.+?)$",
    re.I,
)
R_COND_QUAL = re.compile(r"^(?:the\s+)?(?:lead|it|they|customer|deal)\s+(?:is|are)\s+(?P<neg>not\s+)?qualified$", re.I)
R_COND_VIP = re.compile(r"^(?:the\s+)?(?:customer|lead|they|it|contact)\s+(?:is|are)\s+(?:a\s+)?vip$", re.I)
R_COND_NUM = re.compile(
    r"^(?:the\s+)?(?P<field>budget|amount|deal value|deal size)\s+is\s+(?P<op>over|above|more than|"
    r"greater than|under|below|less than)\s+\$?(?P<n>\d+(?:\.\d+)?)$",
    re.I,
)


class ClauseMatch(BaseModel):
    text: str
    rule: str | None
    step_id: str | None = None


class DraftResult(BaseModel):
    definition: WorkflowDefinition | None
    warnings: list[str] = []
    errors: list[str] = []
    clauses: list[ClauseMatch] = []


@dataclass
class _State:
    trigger: str | None = None
    approval: dict[str, float] = field(default_factory=dict)
    entries: list[Any] = field(default_factory=list)  # dict step | ("cond", cond_step, then_step, else_step)
    ids: set[str] = field(default_factory=set)
    clauses: list[ClauseMatch] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def uid(self, base: str) -> str:
        i, cand = 1, base
        while cand in self.ids:
            i += 1
            cand = f"{base}_{i}"
        self.ids.add(cand)
        return cand


def _clean(s: str) -> str:
    return s.strip().strip(".!?;,").strip()


def _num(s: str) -> float | int:
    f = float(s)
    return int(f) if f.is_integer() else f


def _template(what: str) -> str:
    w = what.lower()
    if any(k in w for k in ("nurture", "welcome", "resources")):
        return "nurture"
    if "reminder" in w and "appointment" in w:
        return "appointment_reminder"
    if "reminder" in w and ("payment" in w or "invoice" in w):
        return "payment_reminder"
    if "thank" in w:
        return "thank_you"
    if "follow" in w or "reminder" in w:
        return "follow_up"
    return re.sub(r"[^a-z0-9]+", "_", w).strip("_")[:40] or "follow_up"


def _step(st: _State, text: str) -> dict | None:
    """Compile one action clause into a step dict (or apply a policy). Returns None if not a step."""
    t = _clean(text)
    if m := R_AGENT.match(t):
        role = ROLES[m["role"].lower()]
        goal = _clean(m["goal"])
        sid = st.uid(role)
        st.clauses.append(ClauseMatch(text=t, rule="agent", step_id=sid))
        return {"id": sid, "type": "agent", "role": role, "goal": goal[:1].upper() + goal[1:]}
    if m := R_DISCOUNT.match(t):
        st.approval["discount_pct_over"] = float(m["n"])
        st.clauses.append(ClauseMatch(text=t, rule="policy"))
        return None
    if m := R_REFUND.match(t):
        st.approval["refund_usd_over"] = float(m["n"])
        st.clauses.append(ClauseMatch(text=t, rule="policy"))
        return None
    if m := R_APPROVAL.match(t):
        who = m["who"].lower()
        desc = f"{who.title()} approval" + (f" before {_clean(m['before'])}" if m["before"] else "")
        sid = st.uid("approval")
        st.clauses.append(ClauseMatch(text=t, rule="approval", step_id=sid))
        return {"id": sid, "type": "approval", "description": desc, "min_role": APPROVER[who]}
    if m := R_WAIT.match(t):
        sid = st.uid("wait")
        st.clauses.append(ClauseMatch(text=t, rule="wait", step_id=sid))
        return {"id": sid, "type": "wait", "seconds": int(m["n"]) * UNITS[m["unit"].lower()]}
    if m := R_NOTIFY.match(t):
        what = _clean(m["what"])
        channel = "sms" if m["verb"].lower() == "text" or re.search(r"\b(text|sms)\b", what, re.I) else "email"
        what = re.sub(r"\s+(?:by\s+)?(?:email|text|sms)$", "", what, flags=re.I)
        sid = st.uid(f"notify_{channel}")
        st.clauses.append(ClauseMatch(text=t, rule="notify", step_id=sid))
        return {"id": sid, "type": "notify", "channel": channel, "template": _template(what)}
    st.clauses.append(ClauseMatch(text=t, rule=None))
    st.warnings.append(f"Didn't understand: '{t}' — it was not added.")
    return None


def _condition(st: _State, text: str) -> bool:
    m = R_IF.match(_clean(text))
    if not m:
        return False
    cond_text = _clean(m["cond"])
    if c := R_COND_QUAL.match(cond_text):
        expr, key = f"blackboard.qualified == {'false' if c['neg'] else 'true'}", "qualified"
    elif R_COND_VIP.match(cond_text):
        expr, key = "blackboard.vip == true", "vip"
    elif c := R_COND_NUM.match(cond_text):
        path = "trigger.budget_usd" if c["field"].lower() == "budget" else "trigger.amount_usd"
        op = ">" if c["op"].lower() in ("over", "above", "more than", "greater than") else "<"
        expr, key = f"{path} {op} {_num(c['n'])}", c["field"].lower().split()[0]
    else:
        st.clauses.append(ClauseMatch(text=_clean(text), rule=None))
        st.warnings.append(f"Didn't understand the condition '{cond_text}' — try 'if the lead is qualified'.")
        return True
    cid = st.uid(f"check_{key}")
    st.clauses.append(ClauseMatch(text=cond_text, rule="condition", step_id=cid))
    then_step = _step(st, m["then"])
    else_step = _step(st, m["else"]) if m["else"] else None
    st.entries.append(("cond", {"id": cid, "type": "condition", "if": expr}, then_step, else_step))
    return True


def _sentences(text: str) -> list[str]:
    text = re.sub(r"(\d),(\d{3})\b", r"\1\2", text)  # 5,000 → 5000 so commas only separate clauses
    return [s for s in (p.strip() for p in re.split(r"(?<=[.!?;])\s+|\n+", text)) if _clean(s)]


def compile_offline(text: str) -> DraftResult:
    if not text or not text.strip():
        return DraftResult(
            definition=None, errors=["Describe the workflow in a sentence or two — start with 'When …'."]
        )
    st = _State()
    for i, sentence in enumerate(_sentences(text)):
        body = _clean(sentence)
        if i == 0 and st.trigger is None:
            if m := R_TRIGGER.match(body):
                st.trigger = NOUN_EVENTS[m["noun"].lower()]
            elif m := R_SCHEDULE.match(body):
                p = m["period"].lower()
                st.trigger = "schedule.daily" if p in ("day", "morning", "weekday") else "schedule.weekly"
            if st.trigger:
                st.clauses.append(ClauseMatch(text=body[: len(body) - len(m["rest"])].strip(" ,"), rule="trigger"))
                body = _clean(m["rest"])
                if not body:
                    continue
        if body.lower().startswith("if ") and _condition(st, body):
            continue
        for clause in re.split(r",?\s+(?:and\s+)?then\s+", body, flags=re.I):
            if step := _step(st, clause):
                st.entries.append(step)

    if st.trigger is None:
        return DraftResult(
            definition=None,
            clauses=st.clauses,
            warnings=st.warnings,
            errors=["Missing trigger — start with 'When …' (e.g. 'When a new lead arrives') or 'Every …'."],
        )
    steps: list[dict] = []
    for idx, entry in enumerate(st.entries):
        if isinstance(entry, dict):
            steps.append(entry)
            continue
        _, cond, then_step, else_step = entry
        cont = "end"
        for later in st.entries[idx + 1 :]:
            cont = later["id"] if isinstance(later, dict) else later[1]["id"]
            break
        cond["then"] = then_step["id"] if then_step else cont
        cond["else"] = else_step["id"] if else_step else cont
        steps.append(cond)
        for branch in (then_step, else_step):
            if branch:
                steps.append({**branch, "next": cont})
    if not steps:
        return DraftResult(
            definition=None,
            clauses=st.clauses,
            warnings=st.warnings,
            errors=["Trigger found but no steps — add something like 'have the sales agent …'."],
        )
    definition = WorkflowDefinition.model_validate(
        {
            "name": f"{EVENT_NAMES.get(st.trigger, st.trigger)} workflow",
            "trigger": {"event": st.trigger},
            "steps": steps,
            "policies": {"approval": st.approval},
        }
    )
    return DraftResult(
        definition=definition, warnings=st.warnings, errors=validate_definition(definition), clauses=st.clauses
    )
