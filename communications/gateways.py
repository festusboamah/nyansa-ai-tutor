import json
from urllib import request as urllib_request

from django.conf import settings
from django.core.mail import send_mail


class EmailGateway:
    name = "django-email"

    def send(self, *, destination, subject, body):
        sent = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [destination], fail_silently=False)
        if sent != 1:
            raise RuntimeError("Email backend did not accept the message.")
        return ""


class ArkeselSmsGateway:
    name = "arkesel"

    def send(self, *, destination, subject, body):
        api_key = getattr(settings, "ARKESEL_API_KEY", "")
        sender_id = getattr(settings, "ARKESEL_SENDER_ID", "Nyansa")
        endpoint = getattr(settings, "ARKESEL_SMS_ENDPOINT", "https://sms.arkesel.com/api/v2/sms/send")
        if not api_key:
            raise RuntimeError("ARKESEL_API_KEY is not configured.")
        payload = json.dumps({
            "sender": sender_id,
            "message": body,
            "recipients": [destination],
        }).encode("utf-8")
        req = urllib_request.Request(
            endpoint, data=payload, method="POST",
            headers={"api-key": api_key, "Content-Type": "application/json"},
        )
        with urllib_request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
        if response.status >= 300:
            raise RuntimeError(f"Arkesel rejected the message with HTTP {response.status}.")
        return str(result.get("data", {}).get("id") or result.get("id") or "")


def gateway_for(channel):
    from .models import MessageTemplate

    if channel == MessageTemplate.Channel.EMAIL:
        return EmailGateway()
    if channel == MessageTemplate.Channel.SMS:
        return ArkeselSmsGateway()
    raise ValueError("Unsupported communication channel.")

