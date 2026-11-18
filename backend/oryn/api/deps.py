"""Request authentication and tenant context.

Two ways in:
* a user JWT plus an ``X-Tenant-Id`` header naming one of the user's tenants, or
* a tenant API key (``Authorization: Bearer oryn_…``), which acts as an operator.
"""

import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, text, update

from oryn.core.db import system_session, tenant_session
from oryn.core.security import AuthError, decode_access_token, hash_api_key, parse_api_key_prefix
from oryn.core.tenancy import Role, role_at_least
from oryn.models import ApiKey, Membership, User


@dataclass(frozen=True)
class TenantContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    role: Role
    via: Literal["user", "api_key"]


def _unauthorized(detail: str = "not authenticated") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized()
    return authorization[7:].strip()


async def current_user(authorization: str | None = Header(default=None)) -> User:
    token = _bearer(authorization)
    try:
        user_id = decode_access_token(token)
    except AuthError as e:
        raise _unauthorized("invalid token") from e
    async with system_session() as s:
        user = await s.get(User, user_id)
    if not user:
        raise _unauthorized("unknown user")
    return user


async def api_key_context(full_key: str) -> TenantContext:
    prefix = parse_api_key_prefix(full_key)
    if not prefix:
        raise _unauthorized("invalid api key")
    async with system_session() as s:
        row = (await s.execute(text("select * from resolve_api_key(:p)"), {"p": prefix})).mappings().first()
    if (
        not row
        or row["revoked_at"] is not None
        or not hmac.compare_digest(row["key_hash"], hash_api_key(full_key))
    ):
        raise _unauthorized("invalid api key")
    async with tenant_session(row["tenant_id"]) as s:
        await s.execute(update(ApiKey).where(ApiKey.id == row["id"]).values(last_used_at=datetime.now(UTC)))
    return TenantContext(tenant_id=row["tenant_id"], user_id=None, role=Role.operator, via="api_key")


async def tenant_ctx(
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> TenantContext:
    token = _bearer(authorization)
    if token.startswith("oryn_"):
        return await api_key_context(token)
    user = await current_user(authorization)
    if not x_tenant_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Tenant-Id header required")
    try:
        tenant_id = uuid.UUID(x_tenant_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid X-Tenant-Id") from e
    async with tenant_session(tenant_id) as s:
        role = (
            await s.execute(select(Membership.role).where(Membership.user_id == user.id))
        ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a member of this tenant")
    return TenantContext(tenant_id=tenant_id, user_id=user.id, role=role, via="user")


def require_role(minimum: Role):
    async def _dep(ctx: TenantContext = Depends(tenant_ctx)) -> TenantContext:
        if not role_at_least(ctx.role, minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role {minimum.value} or higher")
        return ctx

    return _dep
