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
    """The tenant's 'internal warehouse'. Runs inside the caller's tenant session, so RLS
    confines every query to this tenant's sb_* tables. Writes are blocked twice: the
    statement must be a single SELECT/WITH, and it is wrapped as a subquery, where Postgres
    rejects data-modifying CTEs (``WITH x AS (DELETE ...) SELECT ...``)."""

    async def query(self, sql: str, params: dict[str, Any], limit: int = 200) -> QueryResult:
        stmt = assert_read_only(sql)
        await self.faults.maybe_fail("db.query")
        try:
            async with self.s.begin_nested():
                res = await self.s.execute(text(f"select * from ({stmt}) as q limit {int(limit)}"), params)
                cols = list(res.keys())
                rows = [[_jsonable(v) for v in r] for r in res.fetchall()]
        except DBAPIError as e:
            raise NonRetryableConnectorError(f"query failed: {e.orig}", provider="database", status_code=400) from e
        return QueryResult(columns=cols, rows=rows)


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
