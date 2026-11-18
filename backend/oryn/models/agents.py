from decimal import Decimal
from typing import Any

from sqlalchemy import ARRAY, Boolean, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from oryn.models.base import Base, TenantScoped, str_enum
from oryn.models.enums import AgentRole, Autonomy, ConnectorKind


class Connector(Base, TenantScoped):
    __tablename__ = "connectors"
    kind: Mapped[ConnectorKind] = mapped_column(str_enum(ConnectorKind))
    provider: Mapped[str] = mapped_column(String(32), default="sandbox")
    name: Mapped[str] = mapped_column(String(200))
    config_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(32), default="connected")


class Agent(Base, TenantScoped):
    __tablename__ = "agents"
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[AgentRole] = mapped_column(str_enum(AgentRole), index=True)
    channels: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    model: Mapped[str] = mapped_column(String(64), default="claude-opus-5-5")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    allowed_tools: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    autonomy: Mapped[Autonomy] = mapped_column(str_enum(Autonomy), default=Autonomy.act_with_approval)
    max_tokens_per_run: Mapped[int] = mapped_column(Integer, default=20000)
    max_cost_usd_per_run: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.50"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
