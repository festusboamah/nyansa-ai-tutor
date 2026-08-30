import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage
from django.core.exceptions import ImproperlyConfigured


class ResendEmailBackend(BaseEmailBackend):
    """Send Django EmailMessage objects through Resend's HTTPS API."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = settings.RESEND_API_KEY
        self.api_url = settings.RESEND_API_URL
        self.timeout = settings.EMAIL_TIMEOUT

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            error = ImproperlyConfigured("RESEND_API_KEY must be configured for the Resend email backend.")
            if self.fail_silently:
                return 0
            raise error

        sent = 0
        for message in email_messages:
            if not message.recipients():
                continue
            try:
                self._send(message)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError):
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent

    def _send(self, message: EmailMessage):
        payload = self._payload(message)
        request = Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Nyansa/1.0",
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            if not 200 <= response.status < 300:
                raise OSError(f"Resend returned HTTP {response.status}")

    @staticmethod
    def _payload(message: EmailMessage):
        if message.attachments:
            raise ValueError("The Nyansa Resend backend does not currently support attachments.")

        payload = {
            "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
            "to": list(message.to),
            "subject": message.subject,
            "text": message.body,
        }
        if message.cc:
            payload["cc"] = list(message.cc)
        if message.bcc:
            payload["bcc"] = list(message.bcc)
        if message.reply_to:
            payload["reply_to"] = list(message.reply_to)

        for alternative in getattr(message, "alternatives", ()):
            if alternative.mimetype == "text/html":
                payload["html"] = alternative.content
                break
        return payload
