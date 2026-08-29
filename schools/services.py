from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
import hashlib
import secrets

from .models import School, SchoolInvitation, SchoolMembership


ACTIVE_SCHOOL_SESSION_KEY = "active_school_id"


def active_memberships_for(user):
    if not user.is_authenticated:
        return SchoolMembership.objects.none()
    return SchoolMembership.objects.select_related("school").filter(
        user=user,
        status=SchoolMembership.Status.ACTIVE,
        school__status="ACTIVE",
    )


def resolve_active_membership(request):
    memberships = active_memberships_for(request.user)
    selected_school_id = request.session.get(ACTIVE_SCHOOL_SESSION_KEY)

    if selected_school_id is not None:
        selected = memberships.filter(school_id=selected_school_id).first()
        if selected:
            return selected
        request.session.pop(ACTIVE_SCHOOL_SESSION_KEY, None)

    first_membership = memberships.order_by("school_id").first()
    if first_membership and not memberships.exclude(pk=first_membership.pk).exists():
        request.session[ACTIVE_SCHOOL_SESSION_KEY] = first_membership.school_id
        return first_membership
    return None


def select_active_school(request, school):
    membership = active_memberships_for(request.user).filter(school=school).first()
    if not membership:
        raise PermissionDenied("You do not have an active membership in this school.")
    request.session[ACTIVE_SCHOOL_SESSION_KEY] = school.pk
    return membership


def scope_to_school(queryset, school, field="school"):
    if school is None:
        return queryset.none()
    return queryset.filter(**{field: school})


def has_school_role(request, *roles):
    membership = getattr(request, "school_membership", None)
    return bool(membership and membership.is_active and membership.role in roles)


def unique_school_slug(name):
    base = slugify(name)[:70] or "school"
    slug = base
    suffix = 2
    while School.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"[:80]
        suffix += 1
    return slug


def register_school_with_admin(*, name, user):
    """Creates a new School and makes `user` its School Admin, in one step.

    This is the self-serve counterpart to a manually-seeded school: it's what
    lets someone sign up and immediately reach the onboarding wizard, instead
    of needing a school/membership created for them by hand via /admin/.
    """
    with transaction.atomic():
        school = School.objects.create(name=name, slug=unique_school_slug(name))
        SchoolMembership.objects.create(school=school, user=user, role=SchoolMembership.Role.SCHOOL_ADMIN)
    return school


def create_invitation(*, school, email, role, invited_by):
    raw_token = secrets.token_urlsafe(32)
    invitation = SchoolInvitation.objects.create(
        school=school,
        email=email.strip().lower(),
        role=role,
        invited_by=invited_by,
        token_digest=hashlib.sha256(raw_token.encode()).hexdigest(),
    )
    return invitation, raw_token


@transaction.atomic
def accept_invitation(*, raw_token, user):
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    invitation = SchoolInvitation.objects.select_for_update().filter(token_digest=digest).first()
    if not invitation or not invitation.is_usable:
        raise PermissionDenied("This invitation is invalid or has expired.")
    if user.email.strip().lower() != invitation.email:
        raise PermissionDenied("Sign in with the email address that received this invitation.")
    membership, _ = SchoolMembership.objects.update_or_create(
        school=invitation.school,
        user=user,
        defaults={"role": invitation.role, "status": SchoolMembership.Status.ACTIVE},
    )
    invitation.status = SchoolInvitation.Status.ACCEPTED
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["status", "accepted_at"])
    return membership
