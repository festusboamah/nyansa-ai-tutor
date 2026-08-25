"""
Pulls a school's roster (academic year, terms, classes, enrollments,
teaching assignments) from Suku360 and upserts it into Nyansa via
suku360_id, matching docs/suku360-inbound-sync-design.md's proposed
pattern - written back when there was no real Suku360 to sync against,
now implemented against the real thing.

Read-only pull, v1: once a record is Suku360-sourced it's meant to stay
that way going forward (Suku360 is the source of truth), but this pass
doesn't yet enforce read-only-in-Nyansa-UI - it only performs the sync.
"""
import json
import re
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, TeacherAssignment, Term
from courses.models import Subject
from schools.models import SchoolMembership

from .models import SyncBatch, SyncRecord


class Suku360SyncError(Exception):
    pass


def _fetch_roster(credential):
    req = urllib_request.Request(
        f"{credential.base_url.rstrip('/')}/api/v1/integrations/roster/",
        headers={"Authorization": f"Bearer {credential.token}"},
    )
    try:
        with urllib_request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError) as exc:
        raise Suku360SyncError(f"Could not reach Suku360: {exc}") from exc


def _unique_username(school, base_hint):
    User = get_user_model()
    base = re.sub(r"[^a-z0-9]+", "-", f"{school.slug}-{base_hint.lower()}").strip("-")[:140]
    username, suffix = base, 1
    while User.objects.filter(username=username).exists():
        suffix += 1
        username = f"{base[:145]}-{suffix}"
    return username


def _record(batch, entity_type, suku360_id, action, nyansa_object_id="", error_message=""):
    SyncRecord.objects.create(
        batch=batch, entity_type=entity_type, suku360_id=str(suku360_id),
        action=action, nyansa_object_id=str(nyansa_object_id), error_message=error_message,
    )


def get_or_create_membership(*, school, suku360_id, username_hint, first_name, last_name, email, role):
    """Role-agnostic core of _get_or_create_person below, factored out so the
    SSO login handoff (integrations/sso_login.py) can just-in-time create an
    account the same way the roster pull does, without needing a SyncBatch to
    record against. Returns (membership, created)."""
    membership = SchoolMembership.objects.filter(school=school, suku360_id=str(suku360_id)).select_related("user").first()
    if membership:
        user = membership.user
        if user.first_name != first_name or user.last_name != last_name:
            user.first_name, user.last_name = first_name, last_name
            user.save(update_fields=["first_name", "last_name"])
        return membership, False

    User = get_user_model()
    is_staff_like = role in (SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN)
    user = User(
        username=_unique_username(school, username_hint), email=email or "",
        role=User.Role.TEACHER if is_staff_like else User.Role.STUDENT,
    )
    user.set_unusable_password()
    user.first_name, user.last_name = first_name, last_name
    user.save()
    membership = SchoolMembership.objects.create(
        school=school, user=user, role=role, suku360_id=str(suku360_id), portal_access_enabled=False,
    )
    return membership, True


def _get_or_create_person(*, school, batch, entity_type, suku360_id, username_hint, first_name, last_name, email, role):
    membership, created = get_or_create_membership(
        school=school, suku360_id=suku360_id, username_hint=username_hint,
        first_name=first_name, last_name=last_name, email=email, role=role,
    )
    _record(
        batch, entity_type, suku360_id,
        SyncRecord.Action.CREATED if created else SyncRecord.Action.UNCHANGED, membership.pk,
    )
    return membership


@transaction.atomic
def pull_roster(school):
    from .models import Suku360RosterCredential

    credential = Suku360RosterCredential.objects.filter(school=school, is_active=True).first()
    if credential is None:
        raise Suku360SyncError(f"No active Suku360 roster credential configured for {school}.")

    batch = SyncBatch.objects.create(school=school)
    try:
        payload = _fetch_roster(credential)

        for year_data in payload.get("academic_years", []):
            year, created = AcademicYear.objects.update_or_create(
                school=school, name=year_data["name"],
                defaults={"start_date": year_data["start_date"], "end_date": year_data["end_date"]},
            )
            _record(batch, SyncRecord.EntityType.ACADEMIC_YEAR, year_data["id"],
                    SyncRecord.Action.CREATED if created else SyncRecord.Action.UPDATED, year.pk)

            for order, term_data in enumerate(year_data.get("terms", []), start=1):
                term, created = Term.objects.update_or_create(
                    academic_year=year, name=term_data["name"],
                    defaults={"order": order, "start_date": term_data["start_date"], "end_date": term_data["end_date"]},
                )
                _record(batch, SyncRecord.EntityType.TERM, term_data["id"],
                        SyncRecord.Action.CREATED if created else SyncRecord.Action.UPDATED, term.pk)

            terms_by_suku360_id = {
                str(t["id"]): Term.objects.get(academic_year=year, name=t["name"])
                for t in year_data.get("terms", [])
            }

            for class_data in year_data.get("classes", []):
                try:
                    school_class, created = SchoolClass.objects.update_or_create(
                        school=school, suku360_id=str(class_data["id"]),
                        defaults={"academic_year": year, "name": class_data["name"]},
                    )
                except SchoolClass.MultipleObjectsReturned:
                    _record(batch, SyncRecord.EntityType.SCHOOL_CLASS, class_data["id"], SyncRecord.Action.ERROR,
                            error_message="Multiple existing classes matched this suku360_id.")
                    continue
                _record(batch, SyncRecord.EntityType.SCHOOL_CLASS, class_data["id"],
                        SyncRecord.Action.CREATED if created else SyncRecord.Action.UPDATED, school_class.pk)

                for student_data in class_data.get("students", []):
                    try:
                        membership = _get_or_create_person(
                            school=school, batch=batch, entity_type=SyncRecord.EntityType.STUDENT,
                            suku360_id=student_data["id"], username_hint=student_data["student_id_number"],
                            first_name=student_data["first_name"], last_name=student_data["last_name"],
                            email=student_data.get("email", ""), role=SchoolMembership.Role.STUDENT,
                        )
                        _, created = ClassEnrollment.objects.update_or_create(
                            school_class=school_class, student=membership,
                            defaults={"status": ClassEnrollment.Status.ACTIVE},
                        )
                        _record(batch, SyncRecord.EntityType.ENROLLMENT, student_data["id"],
                                SyncRecord.Action.CREATED if created else SyncRecord.Action.UPDATED, membership.pk)
                    except Exception as exc:
                        _record(batch, SyncRecord.EntityType.ENROLLMENT, student_data.get("id", ""),
                                SyncRecord.Action.ERROR, error_message=str(exc)[:500])

                for assignment_data in class_data.get("teaching_assignments", []):
                    try:
                        teacher_membership = _get_or_create_person(
                            school=school, batch=batch, entity_type=SyncRecord.EntityType.TEACHER,
                            suku360_id=assignment_data["teacher_id"], username_hint=assignment_data["teacher_username"],
                            first_name=assignment_data["teacher_first_name"], last_name=assignment_data["teacher_last_name"],
                            email=assignment_data.get("teacher_email", ""), role=SchoolMembership.Role.TEACHER,
                        )
                        subject, _ = Subject.objects.get_or_create(
                            school=school, name=assignment_data["subject_name"],
                        )
                        # Suku360 scopes a teaching assignment per academic year, not per
                        # term - create the Nyansa (term-scoped) equivalent for every term
                        # in this year, matching TeacherAssignment.suku360_id's own docstring.
                        for term in terms_by_suku360_id.values():
                            offering, _ = SubjectOffering.objects.get_or_create(
                                school=school, school_class=school_class, subject=subject, term=term,
                            )
                            _, created = TeacherAssignment.objects.update_or_create(
                                offering=offering, teacher=teacher_membership,
                                defaults={"suku360_id": str(assignment_data["id"])},
                            )
                        _record(batch, SyncRecord.EntityType.TEACHER_ASSIGNMENT, assignment_data["id"],
                                SyncRecord.Action.CREATED if created else SyncRecord.Action.UPDATED)
                    except Exception as exc:
                        _record(batch, SyncRecord.EntityType.TEACHER_ASSIGNMENT, assignment_data.get("id", ""),
                                SyncRecord.Action.ERROR, error_message=str(exc)[:500])

        batch.status = SyncBatch.Status.COMPLETED
    except Suku360SyncError as exc:
        batch.status = SyncBatch.Status.FAILED
        batch.error_message = str(exc)
    finally:
        batch.completed_at = timezone.now()
        batch.save(update_fields=["status", "error_message", "completed_at"])

    return batch
