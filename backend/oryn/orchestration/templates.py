import re
from typing import Any

TEMPLATES: dict[str, tuple[str, str]] = {
    "nurture": (
        "Thanks for reaching out, {{first_name}}",
        "Hi {{first_name}}, thanks for your interest! We'll send a few helpful resources and follow up "
        "when you're ready to talk.",
    ),
    "follow_up": (
        "Following up, {{first_name}}",
        "Hi {{first_name}}, just checking in on your recent request. Reply any time.",
    ),
    "appointment_reminder": (
        "Appointment reminder",
        "Hi {{first_name}}, a reminder about your upcoming appointment. Reply to reschedule.",
    ),
    "payment_reminder": ("Payment reminder", "Hi {{first_name}}, a friendly reminder that an invoice is past due."),
    "thank_you": ("Thank you!", "Hi {{first_name}}, thank you for choosing us."),
}

_VAR = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def _lookup(scope: dict[str, Any], path: str) -> str:
    cur: Any = scope
    for part in path.split("."):
        if not isinstance(cur, dict):
            return ""
        cur = cur.get(part)
    return "" if cur is None else str(cur)


def render(template: str, scope: dict[str, Any]) -> tuple[str, str]:
    subject, body = TEMPLATES.get(template, (template.replace("_", " ").capitalize(), template))
    return _VAR.sub(lambda m: _lookup(scope, m.group(1)), subject), _VAR.sub(lambda m: _lookup(scope, m.group(1)), body)


def notification_scope(trigger: dict[str, Any], blackboard: dict[str, Any]) -> dict[str, Any]:
    name = trigger.get("name") or blackboard.get("contact_name") or "there"
    return {"trigger": trigger, "blackboard": blackboard, "first_name": str(name).split()[0], "name": name}
