import random
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from oryn.connectors.registry import build_connector_set
from oryn.core.config import Settings
from oryn.core.db import tenant_session
from oryn.models import SbCalendarEvent
from oryn.tools.registry import RiskLevel, ToolArgsError, ToolContext, default_registry, from_wire, to_wire
from tests.factories import make_tenant

NOW = datetime(2026, 11, 16, 13, 0, tzinfo=UTC)


def test_specs_for_glob() -> None:
    names = {s.name for s in default_registry().specs_for(["crm.*"])}
    assert "crm.create_deal" in names and "crm.apply_discount" in names
    assert not any(n.startswith("billing.") for n in names)
    assert {n for n in names if n.startswith("control.")} == {
        "control.handoff",
        "control.finish",
        "control.remember",
        "control.escalate_to_human",
        "control.update_blackboard",
    }


def test_validate_args_rejects_bad_types() -> None:
    with pytest.raises(ToolArgsError):
        default_registry().validate_args("crm.apply_discount", {"deal_id": "not-a-uuid", "discount_pct": "lots"})


def test_unknown_tool_is_args_error() -> None:
    with pytest.raises(ToolArgsError):
        default_registry().validate_args("crm.delete_everything", {})


def test_wire_name_roundtrip() -> None:
    assert to_wire("crm.create_deal") == "crm__create_deal"
    assert from_wire("crm__create_deal") == "crm.create_deal"


def test_json_schema_is_anthropic_shape() -> None:
    reg = default_registry()
    schema = reg.json_schema(reg.get("calendar.find_slots").spec)
    assert schema["name"] == "calendar__find_slots"
    assert schema["input_schema"]["type"] == "object"
    assert "duration_min" in schema["input_schema"]["properties"]


def test_high_risk_tools_declare_amount_or_percent_field() -> None:
    for t in default_registry().all_specs():
        if t.risk is RiskLevel.high:
            assert t.amount_field or t.percent_field, t.name
            assert t.side_effect


async def test_invoke_calendar_book_uses_idempotency_key() -> None:
    tenant = await make_tenant("acme")
    reg = default_registry()
    async with tenant_session(tenant.id) as s:
        cs = await build_connector_set(s, tenant.id, Settings(), now=lambda: NOW, rng=random.Random(1))
        ctx = ToolContext(
            tenant_id=tenant.id,
            run_id=uuid.uuid4(),
            agent_id=None,
            session=s,
            connectors=cs,
            idempotency_key="run1:step1:call1",
        )
        slots = await reg.invoke("calendar.find_slots", ctx, {"duration_min": 30, "within_days": 5})
        first = slots["slots"][0]
        args = {"starts_at": first["starts_at"], "ends_at": first["ends_at"], "title": "Consult"}
        r1 = await reg.invoke("calendar.book", ctx, args)
        r2 = await reg.invoke("calendar.book", ctx, args)
        assert r1["id"] == r2["id"]
        assert (await s.execute(select(func.count()).select_from(SbCalendarEvent))).scalar_one() == 1
