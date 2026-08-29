import re

from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse

from .models import SchoolInvitation, SchoolMembership
from .roster_import import _normalise_header, _read_rows
from .services import create_invitation

REQUIRED_HEADERS = {"email", "role"}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ROLE_ALIASES = {code.upper(): code for code in SchoolMembership.Role.values}
_ROLE_ALIASES.update({label.upper(): code for code, label in SchoolMembership.Role.choices})


def parse_staff_invite_list(uploaded_file):
    raw_rows = _read_rows(uploaded_file)
    if not raw_rows:
        raise ValidationError("The file is empty.")
    headers = [_normalise_header(value) for value in raw_rows[0]]
    missing = REQUIRED_HEADERS - set(headers)
    if missing:
        raise ValidationError(f"Missing required column(s): {', '.join(sorted(missing))}.")

    errors, records, seen_emails = [], [], set()
    for row_number, values in enumerate(raw_rows[1:], start=2):
        data = {header: values[index] if index < len(values) else "" for index, header in enumerate(headers) if header in REQUIRED_HEADERS}
        if not any(str(value or "").strip() for value in data.values()):
            continue
        email = str(data.get("email") or "").strip().lower()
        role_raw = str(data.get("role") or "").strip().upper()
        role = _ROLE_ALIASES.get(role_raw, "")

        if not email:
            errors.append(f"Row {row_number}: email is required.")
        elif not _EMAIL_RE.match(email):
            errors.append(f"Row {row_number}: '{email}' doesn't look like a valid email address.")
        elif email in seen_emails:
            errors.append(f"Row {row_number}: duplicate email {email} in this file.")
        seen_emails.add(email)

        if not role:
            valid = ", ".join(code for code in SchoolMembership.Role.values)
            errors.append(f"Row {row_number}: role must be one of {valid} (got '{role_raw}').")

        records.append({"email": email, "role": role})

    if not records:
        errors.append("The file contains no rows.")
    return records, errors


def import_staff_invitations(*, school, records, invited_by, request):
    """
    Sends one invitation email per record. Deliberately not wrapped in a single
    @transaction.atomic block: each row's invitation row and its email send are
    both real side effects, so one bad row shouldn't roll back the successful
    invitations already sent to earlier rows in the same batch.
    """
    results = []
    for record in records:
        email, role = record["email"], record["role"]
        if SchoolInvitation.objects.filter(school=school, email=email, status=SchoolInvitation.Status.PENDING).exists():
            results.append({"email": email, "status": "already_pending"})
            continue
        if SchoolMembership.objects.filter(school=school, user__email__iexact=email).exists():
            results.append({"email": email, "status": "already_member"})
            continue
        try:
            invitation, token = create_invitation(school=school, email=email, role=role, invited_by=invited_by)
            invitation_url = request.build_absolute_uri(reverse("accept_school_invitation", args=[token]))
            send_mail(
                f"Invitation to join {school.name} on Nyansa",
                f"You have been invited as {invitation.get_role_display()}. Accept here: {invitation_url}",
                settings.DEFAULT_FROM_EMAIL,
                [invitation.email],
            )
        except Exception as error:  # noqa: BLE001 - one bad row must not stop the rest of the batch
            results.append({"email": email, "status": "error", "detail": str(error)})
        else:
            results.append({"email": email, "status": "invited"})
    return results
