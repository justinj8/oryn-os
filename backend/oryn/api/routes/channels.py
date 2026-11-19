"""Inbound channels: Twilio SMS + voice webhooks and inbound email. The dashboard's phone and
email simulators post exactly these payloads, so the production code path is what you demo."""

import hashlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from temporalio.client import Client
from twilio.request_validator import RequestValidator

from oryn.api.deps import TenantContext, tenant_ctx
from oryn.api.routes.webhooks import tenant_by_slug
from oryn.channels import twiml
from oryn.core.config import get_settings
from oryn.core.logging import log
from oryn.orchestration.client import temporal_client
from oryn.orchestration.conversation_workflow import AgentReply, UserMessage
from oryn.services.conversations import send_message

router = APIRouter(prefix="/api/webhooks", tags=["channels"])
GREETING = "Hi, thanks for calling. How can I help you today?"


def _xml(body: str) -> Response:
    return Response(content=body, media_type="application/xml")


async def twilio_form(request: Request) -> dict[str, str]:
    """Parses the form and enforces Twilio's request signature when an auth token is configured."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    settings = get_settings()
    if settings.twilio_auth_token:
        url = f"{settings.public_base_url.rstrip('/')}{request.url.path}"
        if request.url.query:  # Twilio signs the full URL, query string included
            url += f"?{request.url.query}"
        sig = request.headers.get("X-Twilio-Signature", "")
        if not RequestValidator(settings.twilio_auth_token.get_secret_value()).validate(url, form, sig):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid Twilio signature")
    else:
        log.debug("twilio.signature_check_skipped", reason="no auth token configured (sandbox mode)")
    return form


@router.post("/{tenant_slug}/twilio/sms")
async def twilio_sms(
    tenant_slug: str, form: dict[str, str] = Depends(twilio_form), client: Client = Depends(temporal_client)
) -> Response:
    tenant = await tenant_by_slug(tenant_slug)
    phone, body = form.get("From", ""), form.get("Body", "").strip()
    if not phone or not body:
        return _xml(twiml.message("Sorry, we couldn't read that message."))
    reply = await send_message(
        client,
        tenant.id,
        "sms",
        phone,
        UserMessage(text=body, message_id=form.get("MessageSid") or _digest(phone, body)),
        contact={"phone": phone},
        address=phone,
    )
    return _xml(twiml.message(reply.text))


@router.post("/{tenant_slug}/twilio/voice")
async def twilio_voice(
    request: Request,
    tenant_slug: str,
    form: dict[str, str] = Depends(twilio_form),
    client: Client = Depends(temporal_client),
) -> Response:
    tenant = await tenant_by_slug(tenant_slug)
    # Each turn's Gather posts back to ?turn=N, so the same words said twice in one call are two turns.
    turn = int(request.query_params.get("turn", "0") or 0)
    base = f"{get_settings().public_base_url.rstrip('/')}{request.url.path}"
    action = f"{base}?turn={turn + 1}"
    call_sid, phone, speech = form.get("CallSid", ""), form.get("From", ""), form.get("SpeechResult", "").strip()
    if not speech:
        return _xml(twiml.gather(GREETING, action))
    reply: AgentReply = await send_message(
        client,
        tenant.id,
        "voice",
        call_sid,
        UserMessage(text=speech, message_id=f"{call_sid}:turn-{turn}"),
        contact={"phone": phone},
        address=phone,
    )
    if reply.status == "ended":
        return _xml(twiml.hangup(reply.text))
    return _xml(twiml.say_and_gather(reply.text, action))


class InboundEmail(BaseModel):
    from_: str = Field(alias="from")
    to: str
    subject: str = ""
    text: str
    message_id: str


@router.post("/{tenant_slug}/email/inbound", response_model=AgentReply)
async def inbound_email(
    tenant_slug: str,
    body: InboundEmail,
    ctx: TenantContext = Depends(tenant_ctx),
    client: Client = Depends(temporal_client),
) -> Any:
    """Inbound email (e.g. from a mail provider's inbound-parse webhook, authenticated by API key)."""
    tenant = await tenant_by_slug(tenant_slug)
    if tenant.id != ctx.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "credentials do not belong to this tenant")
    text = f"{body.subject}\n\n{body.text}".strip() if body.subject else body.text
    return await send_message(
        client,
        tenant.id,
        "email",
        body.from_.lower(),
        UserMessage(text=text, message_id=body.message_id),
        contact={"email": body.from_.lower()},
        address=body.from_.lower(),
        started_by_user_id=ctx.user_id,
    )


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]
