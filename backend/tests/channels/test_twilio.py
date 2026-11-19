import random
from datetime import UTC, datetime

from sqlalchemy import select
from twilio.request_validator import RequestValidator

from oryn.channels import twiml
from oryn.connectors.registry import build_connector_set
from oryn.core.config import Settings, get_settings
from oryn.core.db import owner_session, tenant_session
from oryn.models import SbMessage
from tests.orchestration.wf_helpers import worker

SMS = {"From": "+15550123", "To": "+15550000", "Body": "hello there", "MessageSid": "SM123"}


async def test_sms_webhook_returns_twiml_reply(api, temporal_env, tenant, acts) -> None:
    async with worker(temporal_env.client, acts):
        r = await api.post(f"/api/webhooks/{tenant.slug}/twilio/sms", data=SMS)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    assert "<Message>" in r.text and "help" in r.text.lower()


async def test_duplicate_twilio_message_sid_replies_once(api, temporal_env, tenant, acts) -> None:
    async with worker(temporal_env.client, acts):
        r1 = await api.post(f"/api/webhooks/{tenant.slug}/twilio/sms", data=SMS)
        r2 = await api.post(f"/api/webhooks/{tenant.slug}/twilio/sms", data=SMS)
    assert r1.text == r2.text
    async with owner_session() as s:
        outs = (await s.execute(select(SbMessage).where(SbMessage.direction == "out"))).scalars().all()
    assert len(outs) == 1 and outs[0].channel == "sms" and outs[0].to_addr == "+15550123"


async def test_voice_first_hit_gathers(api, tenant) -> None:
    r = await api.post(f"/api/webhooks/{tenant.slug}/twilio/voice", data={"CallSid": "CA1", "From": "+15550123"})
    assert r.status_code == 200 and "<Gather" in r.text and 'input="speech"' in r.text


async def test_voice_turn_says_reply(api, temporal_env, tenant, acts) -> None:
    async with worker(temporal_env.client, acts):
        r = await api.post(
            f"/api/webhooks/{tenant.slug}/twilio/voice",
            data={"CallSid": "CA1", "From": "+15550123", "SpeechResult": "I need to book an appointment"},
        )
    assert "<Say" in r.text and "openings" in r.text and "<Gather" in r.text


async def test_bad_signature_rejected_when_token_configured(api, tenant) -> None:
    s = get_settings()
    from pydantic import SecretStr

    s.twilio_auth_token = SecretStr("secret-token")
    try:
        r = await api.post(f"/api/webhooks/{tenant.slug}/twilio/sms", data=SMS, headers={"X-Twilio-Signature": "bogus"})
        assert r.status_code == 403
        url = f"{s.public_base_url}/api/webhooks/{tenant.slug}/twilio/voice"
        good = RequestValidator("secret-token").compute_signature(url, {"CallSid": "CA9", "From": "+1"})
        ok = await api.post(
            f"/api/webhooks/{tenant.slug}/twilio/voice",
            data={"CallSid": "CA9", "From": "+1"},
            headers={"X-Twilio-Signature": good},
        )
        assert ok.status_code == 200
    finally:
        s.twilio_auth_token = None


def test_twiml_escapes_xml() -> None:
    xml = twiml.message("Tom & Jerry <3")
    assert "Tom &amp; Jerry &lt;3" in xml
    assert "<Hangup" in twiml.hangup("bye")


class _FakeTwilio:
    def __init__(self) -> None:
        self.sent: list[dict] = []

        class _Msgs:
            def create(inner, **kw):
                self.sent.append(kw)

        self.messages = _Msgs()


async def test_registry_uses_twilio_when_configured(tenant) -> None:
    from oryn.connectors.twilio import TwilioMessaging

    fake = _FakeTwilio()
    settings = Settings(twilio_account_sid="ACtest", twilio_auth_token="tok", twilio_from_number="+15550000")
    async with tenant_session(tenant.id) as s:
        cs = await build_connector_set(s, tenant.id, settings, rng=random.Random(1), now=lambda: datetime.now(UTC))
        assert isinstance(cs.messaging.sms, TwilioMessaging)
        cs.messaging.sms.client = fake
        await cs.messaging.send_sms("+15559999", "Your appointment is confirmed", "k1")
        await cs.messaging.send_sms("+15559999", "Your appointment is confirmed", "k1")  # idempotent
    assert fake.sent == [{"to": "+15559999", "from_": "+15550000", "body": "Your appointment is confirmed"}]


async def test_real_sms_is_not_resent_after_a_step_rolls_back(tenant) -> None:
    """Review finding I6: the dedup record lived in the agent step's transaction, so a rollback
    (a later transient tool failure) erased it and the retry texted the customer again."""
    from oryn.connectors.twilio import TwilioMessaging

    fake = _FakeTwilio()
    settings = Settings(twilio_account_sid="ACtest", twilio_auth_token="tok", twilio_from_number="+15550000")

    class _Boom(Exception):
        pass

    try:
        async with tenant_session(tenant.id) as s:
            cs = await build_connector_set(s, tenant.id, settings, rng=random.Random(1))
            assert isinstance(cs.messaging.sms, TwilioMessaging)
            cs.messaging.sms.client = fake
            await cs.messaging.send_sms("+15559999", "Confirmed", "run1:step:call1")
            raise _Boom  # a later tool in the same step fails transiently → the step rolls back
    except _Boom:
        pass
    async with tenant_session(tenant.id) as s:  # Temporal retries the step
        cs = await build_connector_set(s, tenant.id, settings, rng=random.Random(1))
        cs.messaging.sms.client = fake
        await cs.messaging.send_sms("+15559999", "Confirmed", "run1:step:call1")
    assert len(fake.sent) == 1


async def test_voice_same_words_on_different_turns_both_count(api, temporal_env, tenant, acts) -> None:
    """Review finding I8: turns were deduplicated by sha(CallSid|speech), so saying "yes" twice in
    one call replayed the first answer and dropped the second."""
    import re

    first = await api.post(f"/api/webhooks/{tenant.slug}/twilio/voice", data={"CallSid": "CA7", "From": "+15550123"})
    action = re.search(r'action="([^"]+)"', first.text).group(1)
    assert "turn=1" in action
    async with worker(temporal_env.client, acts):
        await api.post(
            f"/api/webhooks/{tenant.slug}/twilio/voice?turn=1",
            data={"CallSid": "CA7", "From": "+15550123", "SpeechResult": "hello"},
        )
        await api.post(
            f"/api/webhooks/{tenant.slug}/twilio/voice?turn=2",
            data={"CallSid": "CA7", "From": "+15550123", "SpeechResult": "hello"},
        )
    async with owner_session() as s:
        inbound = (await s.execute(select(SbMessage).where(SbMessage.direction == "in"))).scalars().all()
    assert len(inbound) == 2
