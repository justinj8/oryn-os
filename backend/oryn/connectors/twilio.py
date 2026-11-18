"""Real SMS via Twilio. Enabled when TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER are set.

Every send is still recorded in the sandbox outbox (so the dashboard shows it) and keyed by the
idempotency key, so a Temporal retry can never text a customer twice."""

import asyncio
import uuid

from oryn.connectors.base import MessageDTO
from oryn.connectors.errors import ConnectorError
from oryn.connectors.sandbox.messaging import SandboxMessaging


class TwilioMessaging:
    provider = "twilio"

    def __init__(self, account_sid: str, auth_token: str, from_number: str, outbox: SandboxMessaging) -> None:
        from twilio.rest import Client

        self.client = Client(account_sid, auth_token)
        self.from_number = from_number
        self.outbox = outbox

    async def send_sms(
        self, to: str, body: str, idempotency_key: str, conversation_id: uuid.UUID | None = None
    ) -> MessageDTO:
        if (prior := await self.outbox._replay(idempotency_key)) is not None:
            return MessageDTO.model_validate(prior)
        from twilio.base.exceptions import TwilioRestException

        try:
            await asyncio.to_thread(self.client.messages.create, to=to, from_=self.from_number, body=body)
        except TwilioRestException as e:
            raise ConnectorError(str(e.msg), provider="twilio", status_code=e.status) from e
        return await self.outbox.send_sms(to, body, idempotency_key, conversation_id)
