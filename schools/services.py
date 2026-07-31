from django.core.exceptions import PermissionDenied

from .models import SchoolMembership


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
