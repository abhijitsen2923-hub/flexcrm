import asyncio
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.logging import get_logger


logger = get_logger(__name__)


class EmailService:
    async def send_email(self, *, recipient: str, subject: str, body: str) -> None:
        settings = get_settings()
        if not settings.smtp_host:
            logger.info("SMTP is not configured. Skipping email to %s with subject '%s'.", recipient, subject)
            return

        message = EmailMessage()
        message["From"] = settings.smtp_sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        await asyncio.to_thread(self._send_blocking, message)

    def _send_blocking(self, message: EmailMessage) -> None:
        settings = get_settings()
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)

    async def send_welcome_email(self, recipient: str, first_name: str) -> None:
        await self.send_email(
            recipient=recipient,
            subject="Welcome to FlexCRM",
            body=f"Hello {first_name},\n\nYour FlexCRM account is ready. You can now sign in and begin managing customer pipelines.\n",
        )

    async def send_assignment_email(self, recipient: str, assignee_name: str, resource_label: str) -> None:
        await self.send_email(
            recipient=recipient,
            subject=f"New assignment: {resource_label}",
            body=f"Hello {assignee_name},\n\nYou have been assigned to {resource_label}. Please review it in FlexCRM.\n",
        )
