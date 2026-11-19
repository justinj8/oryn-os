import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from oryn.connectors.base import QueryResult
from oryn.connectors.errors import NonRetryableConnectorError
from oryn.connectors.sandbox._common import SandboxBase

_READ_ONLY = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


def assert_read_only(sql: str) -> str:
    stripped = sql.strip().rstrip(";").strip()
    if ";" in stripped:
        raise NonRetryableConnectorError("only a single statement is allowed", provider="database", status_code=400)
    if not _READ_ONLY.match(stripped):
        raise NonRetryableConnectorError("only SELECT queries are allowed", provider="database", status_code=400)
    return stripped


class SandboxDatabase(SandboxBase):
    """The tenant's 'internal warehouse', queried with agent- or MCP-supplied SQL.

    Defense in depth, enforced by Postgres rather than by string filters:
    * the statement runs as ``oryn_warehouse``, which can read only the business tables, not
      users, tenants, API keys or the security-definer functions;
    * that role cannot call ``set_config``, so it cannot switch ``app.tenant_id`` (or its role),
      and RLS keeps every row inside the current tenant;
    * a statement timeout bounds runaway queries;
    * the tenant setting is verified unchanged afterwards, or the result is discarded;
    * only a single SELECT/WITH is accepted, wrapped as a subquery (which rejects data-modifying CTEs).
    """

    STATEMENT_TIMEOUT = "5s"

    async def query(self, sql: str, params: dict[str, Any], limit: int = 200) -> QueryResult:
        stmt = assert_read_only(sql)
        await self.faults.maybe_fail("db.query")
        before = (await self.s.execute(text("select current_setting('app.tenant_id', true)"))).scalar()
        try:
            async with self.s.begin_nested():
                await self.s.execute(text("SET LOCAL ROLE oryn_warehouse"))
                await self.s.execute(text(f"SET LOCAL statement_timeout = '{self.STATEMENT_TIMEOUT}'"))
                res = await self.s.execute(text(f"select * from ({stmt}) as q limit {int(limit)}"), params)
                cols = list(res.keys())
                rows = [[_jsonable(v) for v in r] for r in res.fetchall()]
                await self.s.execute(text("RESET ROLE"))
                await self.s.execute(text("SET LOCAL statement_timeout TO DEFAULT"))
                after = (await self.s.execute(text("select current_setting('app.tenant_id', true)"))).scalar()
                if after != before:
                    raise _TenantChanged()
        except _TenantChanged as e:
            raise NonRetryableConnectorError(
                "query tried to change the tenant context", provider="database", status_code=403
            ) from e
        except DBAPIError as e:
            raise NonRetryableConnectorError(f"query failed: {e.orig}", provider="database", status_code=400) from e
        return QueryResult(columns=cols, rows=rows)


class _TenantChanged(Exception):
    pass


def _jsonable(v: Any) -> Any:
    from datetime import date, datetime
    from decimal import Decimal
    from uuid import UUID

    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    return v
