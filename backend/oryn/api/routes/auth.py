from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, text

from oryn.api.deps import TenantContext, current_user, tenant_ctx
from oryn.core.db import system_session
from oryn.core.security import create_access_token, verify_password
from oryn.models import User

router = APIRouter(prefix="/api", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str


class MembershipOut(BaseModel):
    tenant_id: str
    slug: str
    name: str
    role: str


class SessionOut(BaseModel):
    access_token: str
    user: UserOut
    memberships: list[MembershipOut]


async def _memberships(user: User) -> list[MembershipOut]:
    async with system_session() as s:
        rows = (await s.execute(text("select * from user_memberships(:u)"), {"u": user.id})).mappings()
        return [
            MembershipOut(tenant_id=str(r["tenant_id"]), slug=r["slug"], name=r["name"], role=r["role"])
            for r in rows
        ]


def _user_out(u: User) -> UserOut:
    return UserOut(id=str(u.id), email=u.email, name=u.name)


@router.post("/auth/login", response_model=SessionOut)
async def login(body: LoginIn) -> SessionOut:
    async with system_session() as s:
        user = (await s.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    return SessionOut(
        access_token=create_access_token(user.id), user=_user_out(user), memberships=await _memberships(user)
    )


@router.get("/auth/me", response_model=SessionOut)
async def me(user: User = Depends(current_user)) -> SessionOut:
    return SessionOut(access_token="", user=_user_out(user), memberships=await _memberships(user))


@router.get("/health/tenant", tags=["system"])
async def whoami(ctx: TenantContext = Depends(tenant_ctx)) -> dict[str, str]:
    return {"tenant_id": str(ctx.tenant_id), "role": ctx.role.value, "via": ctx.via}
