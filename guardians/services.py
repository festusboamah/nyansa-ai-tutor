from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from schools.models import SchoolMembership

from .models import GuardianLink


def linked_students(guardian):
    if guardian.role != SchoolMembership.Role.PARENT or not guardian.is_active:
        return SchoolMembership.objects.none()
    return SchoolMembership.objects.filter(
        student_guardian_links__guardian=guardian,
        student_guardian_links__status=GuardianLink.Status.ACTIVE,
        school=guardian.school,
        role=SchoolMembership.Role.STUDENT,
        status=SchoolMembership.Status.ACTIVE,
    ).select_related("user").distinct()


def guardian_can_access(guardian, student):
    return linked_students(guardian).filter(pk=student.pk).exists()


@transaction.atomic
def authorize_link(*, school, guardian, student, relationship, is_primary_contact, authorization_reference, actor):
    if actor.school_id != school.id or actor.role != SchoolMembership.Role.SCHOOL_ADMIN or not actor.is_active:
        raise PermissionDenied("Only an active school administrator can authorize guardian access.")
    link, _ = GuardianLink.objects.select_for_update().get_or_create(
        school=school, guardian=guardian, student=student,
        defaults={"authorized_by": actor, "relationship": relationship, "authorization_reference": authorization_reference},
    )
    link.relationship = relationship
    link.is_primary_contact = is_primary_contact
    link.authorization_reference = authorization_reference.strip()
    link.authorized_by = actor
    link.status = GuardianLink.Status.ACTIVE
    link.revoked_by = None
    link.revoked_at = None
    link.full_clean()
    link.save()
    return link


@transaction.atomic
def revoke_link(*, link, actor):
    link = GuardianLink.objects.select_for_update().get(pk=link.pk)
    if actor.school_id != link.school_id or actor.role != SchoolMembership.Role.SCHOOL_ADMIN or not actor.is_active:
        raise PermissionDenied("Only an active school administrator can revoke guardian access.")
    if link.status == GuardianLink.Status.REVOKED:
        raise ValidationError("Guardian access is already revoked.")
    link.status = GuardianLink.Status.REVOKED
    link.revoked_by = actor
    link.revoked_at = timezone.now()
    link.save(update_fields=["status", "revoked_by", "revoked_at"])
    return link

