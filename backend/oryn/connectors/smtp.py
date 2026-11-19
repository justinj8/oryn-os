"""Real email via SMTP (any provider). Enabled when SMTP_URL is set, e.g. smtp://user:pass@host:587."""

import uuid
from email.message import EmailMessage
from urllib.parse import unquote, urlparse

from oryn.connectors.base import MessageDTO
from oryn.connectors.delivery import already_delivered, mark_delivered
from oryn.connectors.errors import RetryableConnectorError
from oryn.connectors.sandbox.messaging import SandboxMessaging


class SmtpMessaging:
    provider = "smtp"

    def __init__(self, smtp_url: str, from_addr: str, outbox: SandboxMessaging) -> None:
        u = urlparse(smtp_url)
        self.host, self.port = u.hostname or "localhost", u.port or (465 if u.scheme == "smtps" else 587)
        self.user, self.password = unquote(u.username or ""), unquote(u.password or "")
        self.tls = u.scheme == "smtps"
        self.from_addr, self.outbox = from_addr, outbox

    async def send_email(
        self, to: str, subject: str, body: str, idempotency_key: str, conversation_id: uuid.UUID | None = None
    ) -> MessageDTO:
        if (prior := await self.outbox._replay(idempotency_key)) is not None:
            return MessageDTO.model_validate(prior)
        import aiosmtplib

        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.from_addr, to, subject
        msg["Message-ID"] = f"<{idempotency_key.replace(':', '.')}@oryn>"
        msg.set_content(body)
        if not await already_delivered(self.outbox.tenant_id, idempotency_key):
            try:
                await aiosmtplib.send(
                    msg,
                    hostname=self.host,
                    port=self.port,
                    username=self.user or None,
                    password=self.password or None,
                    use_tls=self.tls,
                    start_tls=not self.tls,
                )
            except (aiosmtplib.SMTPException, OSError) as e:
                raise RetryableConnectorError(f"smtp: {e}", provider="smtp") from e
            await mark_delivered(self.outbox.tenant_id, idempotency_key, "smtp")
        return await self.outbox.send_email(to, subject, body, idempotency_key, conversation_id)
