"""Receives the one-time "here's a new roster credential" push Suku360 sends
when a PartnerCredential is issued/rotated in its own admin
(domains.integrations.admin.PartnerCredentialAdmin.save_model on that side),
so the credential handoff and first sync happen automatically instead of
someone copying a token by hand and running pull_suku360_roster themselves."""
import hashlib
import hmac
import json

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError

from schools.models import School

from .models import Suku360RosterCredential
from .suku360_sync import Suku360SyncError, pull_roster


def process_suku360_credential_webhook(*, raw_body, signature):
    if not settings.SUKU360_WEBHOOK_SECRET:
        raise PermissionDenied("Suku360 webhook is not configured for this deployment.")
    expected = hmac.new(settings.SUKU360_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        raise PermissionDenied("Invalid Suku360 webhook signature.")

    payload = json.loads(raw_body.decode("utf-8"))
    slug = payload["nyansa_school_slug"]
    school = School.objects.filter(slug=slug).first()
    if school is None:
        raise ValidationError(f"Unknown Nyansa school slug: {slug}")

    credential, _ = Suku360RosterCredential.objects.update_or_create(
        school=school,
        defaults={"token": payload["token"], "base_url": payload["base_url"], "is_active": True},
    )

    try:
        pull_roster(school)
    except Suku360SyncError:
        # The credential is what must be preserved here - a transient pull
        # failure shouldn't block registering it. pull_suku360_roster (or
        # the next webhook delivery, e.g. a token rotation) can retry later.
        pass

    return credential
