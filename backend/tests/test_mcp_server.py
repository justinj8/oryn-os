import json

from sqlalchemy import select

from oryn.core.db import owner_session
from oryn.mcp_server import OrynMcpTools
from oryn.models import Approval
from tests.orchestration.wf_helpers import worker


async def test_mcp_lists_tools_without_control(tenant, temporal_env) -> None:
    tools = OrynMcpTools(tenant.id, temporal_env.client).list_tools()
    names = {t["name"] for t in tools}
    assert "crm__find_contact" in names and "billing__issue_refund" in names
    assert not any(n.startswith("control__") for n in names)
    refund = next(t for t in tools if t["name"] == "billing__issue_refund")
    assert "requires human approval" in refund["description"]


async def test_mcp_readonly_tool_executes(tenant, temporal_env) -> None:
    out = await OrynMcpTools(tenant.id, temporal_env.client).call_tool("docs__search", {"query": "refund policy"})
    assert out["status"] == "ok" and out["result"]["hits"][0]["title"] == "Refund policy"


async def test_mcp_high_risk_tool_requests_approval(tenant, temporal_env, acts, invoice) -> None:
    async with worker(temporal_env.client, acts):
        out = await OrynMcpTools(tenant.id, temporal_env.client).call_tool(
            "billing__issue_refund", {"invoice_id": str(invoice), "amount_usd": 100}
        )
    assert out["status"] == "approval_requested"
    async with owner_session() as s:
        a = (await s.execute(select(Approval))).scalar_one()
    assert str(a.id) == out["approval_id"] and a.action_tool == "billing.issue_refund"


async def test_mcp_bad_args_reported(tenant, temporal_env) -> None:
    out = await OrynMcpTools(tenant.id, temporal_env.client).call_tool("calendar__find_slots", {"duration_min": 2})
    assert out["status"] == "error" and "invalid arguments" in out["error"]
    json.dumps(out)


async def test_build_mcp_server_wires_handlers(tenant, temporal_env) -> None:
    import mcp_types as types

    from oryn.mcp_server import build_mcp_server

    server = build_mcp_server(OrynMcpTools(tenant.id, temporal_env.client))
    assert server.get_request_handler("tools/list") is not None
    assert server.get_request_handler("tools/call") is not None
    assert isinstance(server.create_initialization_options(), object)
    _ = types
