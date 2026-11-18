"""Members, API keys and the audit log."""

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from oryn.api.deps import TenantContext, require_role
from oryn.core.audit import record_audit
from oryn.core.db import tenant_session
from oryn.core.security import generate_api_key, hash_password
from oryn.core.tenancy import Role
from oryn.models import ApiKey, AuditLog, Membership, User

router = APIRouter(prefix="/api", tags=["admin"])


class MemberOut(BaseModel):
    user_id: str
    email: str
    name: str
    role: Role


class MemberIn(BaseModel):
    # Plain pattern on purpose: demo tenants use reserved .test domains that EmailStr rejects.
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str
    role: Role
    password: str | None = None


class MemberPatch(BaseModel):
    role: Role


@router.get("/members", response_model=list[MemberOut])
async def list_members(ctx: TenantContext = Depends(require_role(Role.viewer))) -> list[MemberOut]:
    async with tenant_session(ctx.tenant_id) as s:
        rows = await s.execute(
            select(User, Membership.role).join(Membership, Membership.user_id == User.id).order_by(User.name)
        )
        return [MemberOut(user_id=str(u.id), email=u.email, name=u.name, role=r) for u, r in rows]


@router.post("/members", response_model=MemberOut, status_code=201)
async def invite_member(body: MemberIn, ctx: TenantContext = Depends(require_role(Role.owner))) -> MemberOut:
    email = body.email.lower()
    async with tenant_session(ctx.tenant_id) as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            user = User(
                email=email,
                name=body.name,
                password_hash=hash_password(body.password or secrets.token_urlsafe(24)),
            )
            s.add(user)
            await s.flush()
        exists = (
            await s.execute(select(Membership).where(Membership.user_id == user.id))
        ).scalar_one_or_none()
        if exists:
            raise HTTPException(status.HTTP_409_CONFLICT, "already a member")
        s.add(Membership(tenant_id=ctx.tenant_id, user_id=user.id, role=body.role))
        await record_audit(s, ctx, "member.created", "user", user.id, after={"role": body.role.value})
        return MemberOut(user_id=str(user.id), email=user.email, name=user.name, role=body.role)


@router.patch("/members/{user_id}", response_model=MemberOut)
async def change_role(
    user_id: uuid.UUID, body: MemberPatch, ctx: TenantContext = Depends(require_role(Role.owner))
) -> MemberOut:
    async with tenant_session(ctx.tenant_id) as s:
        m = (await s.execute(select(Membership).where(Membership.user_id == user_id))).scalar_one_or_none()
        if not m:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")
        if user_id == ctx.user_id and body.role != Role.owner:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "owners cannot demote themselves")
        before = m.role
        m.role = body.role
        user = await s.get(User, user_id)
        assert user
        await record_audit(
            s, ctx, "member.role_changed", "user", user_id, {"role": before.value}, {"role": body.role.value}
        )
        return MemberOut(user_id=str(user.id), email=user.email, name=user.name, role=body.role)


class ApiKeyIn(BaseModel):
    name: str


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str


def _key_out(k: ApiKey) -> dict:
    return {
        "id": str(k.id),
        "name": k.name,
        "prefix": k.prefix,
        "created_at": k.created_at,
        "last_used_at": k.last_used_at,
        "revoked_at": k.revoked_at,
    }


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_keys(ctx: TenantContext = Depends(require_role(Role.owner))) -> list[dict]:
    async with tenant_session(ctx.tenant_id) as s:
        keys = (await s.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))).scalars().all()
        return [_key_out(k) for k in keys]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_key(body: ApiKeyIn, ctx: TenantContext = Depends(require_role(Role.owner))) -> dict:
    full, prefix, key_hash = generate_api_key()
    async with tenant_session(ctx.tenant_id) as s:
        k = ApiKey(
            tenant_id=ctx.tenant_id, name=body.name, prefix=prefix, key_hash=key_hash, created_by=ctx.user_id
        )
        s.add(k)
        await s.flush()
        await s.refresh(k)
        await record_audit(s, ctx, "api_key.created", "api_key", k.id, after={"name": body.name})
        return {**_key_out(k), "key": full}


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_key(key_id: uuid.UUID, ctx: TenantContext = Depends(require_role(Role.owner))) -> Response:
    async with tenant_session(ctx.tenant_id) as s:
        k = await s.get(ApiKey, key_id)
        if not k:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found")
        k.revoked_at = datetime.now(UTC)
        await record_audit(s, ctx, "api_key.revoked", "api_key", k.id)
    return Response(status_code=204)


class AuditOut(BaseModel):
    id: str
    actor_user_id: str | None
    action: str
    target_type: str
    target_id: str | None
    before: dict | None
    after: dict | None
    created_at: datetime


@router.get("/audit", response_model=list[AuditOut])
async def list_audit(
    limit: int = 100, ctx: TenantContext = Depends(require_role(Role.admin))
) -> list[AuditOut]:
    async with tenant_session(ctx.tenant_id) as s:
        rows = (
            (await s.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))))
            .scalars()
            .all()
        )
        return [
            AuditOut(
                id=str(a.id),
                actor_user_id=str(a.actor_user_id) if a.actor_user_id else None,
                action=a.action,
                target_type=a.target_type,
                target_id=str(a.target_id) if a.target_id else None,
                before=a.before,
                after=a.after,
                created_at=a.created_at,
            )
            for a in rows
        ]
