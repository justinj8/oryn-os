"""Oryn OS as an MCP server: expose a tenant's tool registry to any MCP client (e.g. Claude).

    ORYN_API_KEY=oryn_xxx python -m oryn.mcp_server            # stdio
    ORYN_API_KEY=oryn_xxx python -m oryn.mcp_server --http      # streamable HTTP on :8765

Read-only tools run immediately. Side-effecting tools are never executed directly: they start a
``McpActionWorkflow`` that waits for a human approval in the Oryn dashboard, exactly like an agent's
risky action would.
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

import mcp_types as types
from sqlalchemy import select
from temporalio.client import Client

from oryn.connectors.registry import build_connector_set
from oryn.core.config import get_settings
from oryn.core.db import tenant_session
from oryn.models import Approval, Autonomy, Run, RunStatus
from oryn.orchestration.client import get_task_queue
from oryn.policies.approval import ProposedAction, WorkflowPolicies, evaluate_approval
from oryn.tools.registry import ToolArgsError, ToolContext, default_registry, from_wire

APPROVAL_WAIT_S = 10.0


class OrynMcpTools:
    """Transport-independent core of the MCP server (unit-tested directly)."""

    def __init__(self, tenant_id: uuid.UUID, client: Client) -> None:
        self.tenant_id, self.client = tenant_id, client
        self.registry = default_registry()

    def list_tools(self) -> list[dict[str, Any]]:
        out = []
        for spec in self.registry.all_specs():
            if spec.is_control:
                continue
            schema = self.registry.json_schema(spec)
            if spec.side_effect:
                schema["description"] += " (Side effect: requires human approval in Oryn OS before it runs.)"
            out.append(schema)
        return out

    async def call_tool(self, wire_name: str, args: dict[str, Any]) -> dict[str, Any]:
        name = from_wire(wire_name)
        try:
            spec = self.registry.get(name).spec
            self.registry.validate_args(name, args)
        except ToolArgsError as e:
            return {"status": "error", "error": str(e)}
        if spec.is_control:
            return {"status": "error", "error": "control tools are internal"}
        if not spec.side_effect:
            return await self._run_now(name, args)
        req = evaluate_approval(ProposedAction.from_spec(spec, args), Autonomy.act_with_approval, WorkflowPolicies())
        return await self._request_approval(name, args, list(req.reasons), req.min_role)

    async def _run_now(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        try:
            async with tenant_session(self.tenant_id) as s:
                cs = await build_connector_set(s, self.tenant_id, settings)
                ctx = ToolContext(
                    tenant_id=self.tenant_id,
                    run_id=uuid.uuid4(),
                    agent_id=None,
                    session=s,
                    connectors=cs,
                    idempotency_key=f"mcp:{uuid.uuid4()}",
                )
                return {"status": "ok", "result": await self.registry.invoke(name, ctx, args)}
        except Exception as e:  # report, don't crash the MCP session
            return {"status": "error", "error": str(e)}

    async def _request_approval(self, name, args, reasons, min_role) -> dict[str, Any]:
        from oryn.orchestration.mcp_action_workflow import McpActionInput, McpActionWorkflow

        run_id = uuid.uuid4()
        wf_id = f"{self.tenant_id}:mcp:{run_id}"
        key = f"mcp:{run_id}"
        async with tenant_session(self.tenant_id) as s:
            s.add(
                Run(
                    id=run_id,
                    tenant_id=self.tenant_id,
                    kind="mcp_action",
                    title=f"MCP · {name}",
                    temporal_workflow_id=wf_id,
                    status=RunStatus.running,
                    started_at=datetime.now(UTC),
                )
            )
        await self.client.start_workflow(
            McpActionWorkflow.run,
            McpActionInput(
                tenant_id=self.tenant_id,
                run_id=run_id,
                tool=name,
                args=args,
                idempotency_key=key,
                description=f"MCP client requests {name}",
                reasons=["requested by an external MCP client", *reasons],
                min_role=min_role or "operator",
            ),
            id=wf_id,
            task_queue=get_task_queue(),
        )
        deadline = asyncio.get_running_loop().time() + APPROVAL_WAIT_S
        while asyncio.get_running_loop().time() < deadline:
            async with tenant_session(self.tenant_id) as s:
                a = (await s.execute(select(Approval.id).where(Approval.idempotency_key == key))).scalar_one_or_none()
            if a:
                return {
                    "status": "approval_requested",
                    "approval_id": str(a),
                    "run_id": str(run_id),
                    "message": "A human must approve this in the Oryn OS dashboard before it runs.",
                }
            await asyncio.sleep(0.2)
        return {"status": "approval_requested", "run_id": str(run_id)}


def build_mcp_server(tools: OrynMcpTools):
    from mcp.server.lowlevel import Server

    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(name=t["name"], description=t["description"], inputSchema=t["input_schema"])
                for t in tools.list_tools()
            ]
        )

    async def on_call_tool(ctx, params) -> types.CallToolResult:
        out = await tools.call_tool(params.name, dict(params.arguments or {}))
        return types.CallToolResult(
            content=[types.TextContent(text=json.dumps(out, default=str))], isError=out.get("status") == "error"
        )

    return Server("oryn-os", on_list_tools=on_list_tools, on_call_tool=on_call_tool)


async def _main() -> None:
    from mcp.server.stdio import stdio_server

    from oryn.api.deps import api_key_context
    from oryn.orchestration.client import get_temporal_client

    key = os.environ.get("ORYN_API_KEY")
    if not key:
        sys.exit("set ORYN_API_KEY to a tenant API key (create one in Settings → API keys)")
    ctx = await api_key_context(key)
    server = build_mcp_server(OrynMcpTools(ctx.tenant_id, await get_temporal_client()))
    if "--http" in sys.argv:
        import uvicorn

        await uvicorn.Server(uvicorn.Config(server.streamable_http_app(), host="0.0.0.0", port=8765)).serve()
        return
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
