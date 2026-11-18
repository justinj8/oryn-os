from sqlalchemy import select

from oryn.core.db import owner_session
from oryn.models import SbMessage
from tests.orchestration.wf_helpers import worker


async def test_email_inbound_replies_by_email(api, temporal_env, tenant, acts) -> None:
    owner_key = None
    from oryn.core.tenancy import Role
    from tests.factories import auth_headers, make_member

    o = await make_member(tenant, Role.owner)
    owner_key = (await api.post("/api/api-keys", headers=auth_headers(o, tenant), json={"name": "mail"})).json()["key"]
    async with worker(temporal_env.client, acts):
        r = await api.post(
            f"/api/webhooks/{tenant.slug}/email/inbound",
            headers={"Authorization": f"Bearer {owner_key}"},
            json={
                "from": "ann@example.com",
                "to": "help@acme.test",
                "subject": "Refund policy?",
                "text": "What is your refund policy?",
                "message_id": "<m1@mail>",
            },
        )
    assert r.status_code == 200 and r.json()["status"] == "ok"
    async with owner_session() as s:
        out = (await s.execute(select(SbMessage).where(SbMessage.direction == "out"))).scalar_one()
    assert out.channel == "email" and out.to_addr == "ann@example.com" and "30 days" in out.body
