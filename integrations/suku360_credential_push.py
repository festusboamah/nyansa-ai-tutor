"""Pushes a freshly generated IntegrationCredential to Suku360 - the reverse
direction from webhook_push.py/suku360_webhook.py (Suku360 pushing a
PartnerCredential to Nyansa). Same HMAC-SHA512-of-raw-body scheme, same
shared SUKU360_WEBHOOK_SECRET, using urllib like every other outbound call
in this codebase (finance/gateways.py, suku360_sync.py) rather than adding
`requests` as a new dependency."""
import hashlib
import hmac
import json
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from django.conf import settings


class CredentialPushError(Exception):
    """Raised when the token can't be delivered to Suku360 - callers must
    not let this prevent the credential itself from being saved; the school
    admin can still copy the token to Suku360's admin by hand."""


def push_credential_to_suku360(*, suku360_school_id, raw_token):
    if not settings.SUKU360_WEBHOOK_SECRET or not settings.SUKU360_BASE_URL:
        raise CredentialPushError("SUKU360_WEBHOOK_SECRET/SUKU360_BASE_URL is not configured for this deployment.")

    payload = {"suku360_school_id": suku360_school_id, "token": raw_token}
    raw_body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(settings.SUKU360_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    req = urllib_request.Request(
        f"{settings.SUKU360_BASE_URL.rstrip('/')}/api/v1/integrations/webhook/credential/",
        data=raw_body, method="POST",
        headers={"Content-Type": "application/json", "X-Nyansa-Signature": signature},
    )
    try:
        urllib_request.urlopen(req, timeout=10)
    except (HTTPError, URLError) as exc:
        raise CredentialPushError(f"Could not reach Suku360: {exc}") from exc
