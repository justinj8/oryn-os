"""Keyword intent classifier used by the offline Replay model."""

import re
from enum import StrEnum


class Intent(StrEnum):
    book_appointment = "book_appointment"
    reschedule = "reschedule"
    select_slot = "select_slot"
    pricing = "pricing"
    refund = "refund"
    billing_question = "billing_question"
    support_issue = "support_issue"
    greeting = "greeting"
    goodbye = "goodbye"
    unknown = "unknown"


_RULES: list[tuple[Intent, tuple[str, ...]]] = [
    # Questions *about* a policy are knowledge-base questions, not requests to act.
    (Intent.support_issue, ("policy", "policies", "how do refunds work")),
    (Intent.refund, ("refund", "money back", "chargeback", "overcharged")),
    (Intent.reschedule, ("reschedule", "move my appointment", "change my appointment", "cancel my appointment")),
    (
        Intent.select_slot,
        (
            "first one",
            "second one",
            "third one",
            "that works",
            "works for me",
            "option 1",
            "option 2",
            "option 3",
            "the first",
            "the second",
            "the third",
        ),
    ),
    (
        Intent.book_appointment,
        (
            "book",
            "appointment",
            "schedule",
            "visit",
            "consult",
            "come out",
            "availability",
            "available",
            "cleaning",
            "checkup",
        ),
    ),
    (Intent.pricing, ("price", "cost", "quote", "how much", "estimate", "pricing")),
    (Intent.billing_question, ("invoice", "bill", "payment", "charge", "receipt")),
    (
        Intent.support_issue,
        (
            "broken",
            "not working",
            "noise",
            "leak",
            "problem",
            "issue",
            "help",
            "error",
            "won't",
            "doesn't",
            "stopped",
            "warranty",
            "policy",
            "hours",
            "pain",
            "tooth",
        ),
    ),
    (Intent.goodbye, ("thanks", "thank you", "bye", "that's all")),
    (Intent.greeting, ("hello", "hi ", "hey", "good morning", "good afternoon")),
]


def classify(text: str) -> Intent:
    t = f" {text.lower().strip()} "
    for intent, words in _RULES:
        if any(w in t for w in words):
            return intent
    if re.fullmatch(r"\s*(hi|hey|hello)[!. ]*", t):
        return Intent.greeting
    return Intent.unknown


def slot_choice(text: str) -> int | None:
    t = text.lower()
    for i, words in enumerate((("first", "1", "one"), ("second", "2", "two"), ("third", "3", "three"))):
        if any(re.search(rf"\b{w}\b", t) for w in words):
            return i
    if any(w in t for w in ("that works", "works for me", "yes", "sounds good", "perfect")):
        return 0
    return None
