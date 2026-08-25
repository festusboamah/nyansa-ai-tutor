"""Verifies the short-lived signed token Suku360's launch endpoint
(domains/integrations/sso.py on that side) mints, then logs the matching
Nyansa account in - the receiving half of the SSO handoff. Same
HMAC-SHA512-of-payload verification scheme as the credential webhook
(suku360_webhook.py), just a different payload shape and, unlike the
webhook, a single-use nonce check (see SsoNonce) since a leaked/logged URL
being replayed here means signing in as that person, not just re-syncing a
roster."""
import base64
import binascii
import hashlib
import hmac
import json
import time

from django.conf import settings
from django.contrib.auth import login as auth_login
from django.core.exceptions import PermissionDenied, ValidationError

from schools.models import School, SchoolMembership
from schools.services import select_active_school

from .models import SsoNonce
from .suku360_sync import get_or_create_membership

ROLE_MAP = {
    "headteacher": SchoolMembership.Role.SCHOOL_ADMIN,
    "teacher": SchoolMembership.Role.TEACHER,
    "student": SchoolMembership.Role.STUDENT,
}


def _verify_and_decode(token):
    try:
        payload_b64, signature_b64 = token.split(".")
        payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
        signature = base64.urlsafe_b64decode(signature_b64.encode("ascii"))
    except (ValueError, TypeError, binascii.Error):
        raise ValidationError("Malformed SSO token.")

    if not settings.SUKU360_WEBHOOK_SECRET:
        raise PermissionDenied("Suku360 SSO is not configured for this deployment.")
    expected = hmac.new(settings.SUKU360_WEBHOOK_SECRET.encode("utf-8"), payload_bytes, hashlib.sha512).digest()
    if not hmac.compare_digest(expected, signature):
        raise PermissionDenied("Invalid SSO token signature.")

    payload = json.loads(payload_bytes.decode("utf-8"))
    if int(time.time()) > payload["exp"]:
        raise PermissionDenied("This sign-in link has expired.")
    return payload


def login_from_suku360_token(request, token):
    """Verifies `token`, resolves (or just-in-time creates) the matching
    Nyansa account, and logs it into `request`. Returns the School logged
    into. Raises PermissionDenied (expired/invalid/replayed/unconfigured) or
    ValidationError (malformed/unknown school or role) - callers translate
    these into the appropriate HTTP response, same split as
    suku360_webhook.py."""
    payload = _verify_and_decode(token)

    _, created = SsoNonce.objects.get_or_create(nonce=payload["nonce"])
    if not created:
        raise PermissionDenied("This sign-in link has already been used.")

    school = School.objects.filter(slug=payload["nyansa_school_slug"]).first()
    if school is None:
        raise ValidationError(f"Unknown Nyansa school slug: {payload['nyansa_school_slug']}")

    role = ROLE_MAP.get(payload["role"])
    if role is None:
        raise ValidationError(f"Unrecognised Suku360 role: {payload['role']}")

    membership, _ = get_or_create_membership(
        school=school, suku360_id=payload["suku360_id"],
        username_hint=payload.get("email") or payload["first_name"],
        first_name=payload["first_name"], last_name=payload["last_name"],
        email=payload.get("email", ""), role=role,
    )

    auth_login(request, membership.user)
    select_active_school(request, school)
    return school
