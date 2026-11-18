"""The tool registry: one typed, risk-annotated catalog shared by agents and the MCP server."""

import fnmatch
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from oryn.connectors.registry import ConnectorSet
from oryn.models import ConnectorKind


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class ToolArgsError(ValueError):
    """Arguments failed validation, or the tool does not exist. Never retryable."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    risk: RiskLevel
    side_effect: bool
    connector: ConnectorKind | None
    amount_field: str | None = None
    percent_field: str | None = None

    @property
    def is_control(self) -> bool:
        return self.name.startswith("control.")


@dataclass
class ToolContext:
    tenant_id: uuid.UUID
    run_id: uuid.UUID
    agent_id: uuid.UUID | None
    session: AsyncSession
    connectors: ConnectorSet
    idempotency_key: str


Handler = Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class RegisteredTool:
    spec: ToolSpec
    handler: Handler


def to_wire(name: str) -> str:
    """Tool names on the LLM wire can't contain dots."""
    return name.replace(".", "__")


def from_wire(name: str) -> str:
    return name.replace("__", ".")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, spec: ToolSpec, handler: Handler) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool {spec.name}")
        self._tools[spec.name] = RegisteredTool(spec, handler)

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as e:
            raise ToolArgsError(f"unknown tool '{name}'") from e

    def all_specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def specs_for(self, allowed: Sequence[str]) -> list[ToolSpec]:
        """Tools matching any allowed glob (e.g. ``crm.*``), plus every control tool."""
        return [
            t.spec
            for t in self._tools.values()
            if t.spec.is_control or any(fnmatch.fnmatchcase(t.spec.name, pat) for pat in allowed)
        ]

    def validate_args(self, name: str, args: dict[str, Any]) -> BaseModel:
        spec = self.get(name).spec
        try:
            return spec.input_model.model_validate(args)
        except ValidationError as e:
            raise ToolArgsError(f"invalid arguments for {name}: {e.errors(include_url=False)}") from e

    def json_schema(self, spec: ToolSpec) -> dict[str, Any]:
        schema = spec.input_model.model_json_schema()
        schema.pop("title", None)
        return {"name": to_wire(spec.name), "description": spec.description, "input_schema": schema}

    async def invoke(self, name: str, ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        tool = self.get(name)
        parsed = self.validate_args(name, args)
        return await tool.handler(ctx, parsed)


_default: ToolRegistry | None = None


def default_registry() -> ToolRegistry:
    global _default
    if _default is None:
        from oryn.tools.catalog import register_catalog
        from oryn.tools.control import register_control

        reg = ToolRegistry()
        register_catalog(reg)
        register_control(reg)
        _default = reg
    return _default
