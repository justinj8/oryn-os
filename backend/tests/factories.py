"""Test data factories. They write through the owner session (bypasses RLS)."""

import uuid

from oryn.core.db import owner_session
from oryn.core.security import create_access_token, hash_password
from oryn.core.tenancy import Role
from oryn.models import Membership, Tenant, User


async def make_tenant(slug: str = "acme", name: str | None = None, **settings) -> Tenant:
    t = Tenant(id=uuid.uuid4(), slug=slug, name=name or slug.title(), settings=settings)
    async with owner_session() as s:
        s.add(t)
    return t


async def make_user(email: str = "u@acme.test", password: str = "pw", name: str = "User") -> User:
    u = User(id=uuid.uuid4(), email=email, name=name, password_hash=hash_password(password))
    async with owner_session() as s:
        s.add(u)
    return u


async def make_membership(tenant: Tenant, user: User, role: Role) -> Membership:
    m = Membership(tenant_id=tenant.id, user_id=user.id, role=role)
    async with owner_session() as s:
        s.add(m)
    return m


async def make_member(tenant: Tenant, role: Role, email: str | None = None) -> User:
    user = await make_user(email or f"{role.value}-{uuid.uuid4().hex[:6]}@{tenant.slug}.test")
    await make_membership(tenant, user, role)
    return user


def auth_headers(user: User, tenant: Tenant | None = None) -> dict[str, str]:
    h = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    if tenant:
        h["X-Tenant-Id"] = str(tenant.id)
    return h
