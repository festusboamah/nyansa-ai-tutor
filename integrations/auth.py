import hashlib

from django.utils import timezone

from .models import IntegrationCredential


def authenticate_request(request):
    """Resolves the School a Bearer-token API request belongs to, or None.
    The school is always derived from the verified credential - never trusted
    from a request parameter - matching this codebase's tenancy discipline."""
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        return None
    token = header[len("Bearer "):].strip()
    if not token:
        return None

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    credential = IntegrationCredential.objects.filter(
        token_hash=token_hash, is_active=True
    ).select_related("school").first()
    if credential is None:
        return None

    credential.last_used_at = timezone.now()
    credential.save(update_fields=["last_used_at"])
    return credential.school
