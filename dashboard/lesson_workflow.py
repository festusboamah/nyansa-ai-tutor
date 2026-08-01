from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from schools.models import SchoolMembership
from communications.models import Notification
from communications.services import create_notification, notify_school_role

from .models import LessonNote, LessonNoteEvent, LessonNoteNotification, LessonNoteVersion


SNAPSHOT_FIELDS = (
    "class_level", "strand_topic", "content_standard", "learning_indicator",
    "performance_indicator", "reference", "resources", "num_days", "generated_content",
)


def _author_membership(note):
    return SchoolMembership.objects.filter(
        school=note.subject.school,
        user=note.teacher,
        role=SchoolMembership.Role.TEACHER,
        status=SchoolMembership.Status.ACTIVE,
    ).first()


def _require_author(note, actor):
    if (
        actor.school_id != note.subject.school_id
        or actor.role != SchoolMembership.Role.TEACHER
        or actor.user_id != note.teacher_id
    ):
        raise PermissionDenied("Only the lesson-note author can perform this action.")


def _require_reviewer(note, actor):
    if actor.school_id != note.subject.school_id or actor.role != SchoolMembership.Role.SCHOOL_ADMIN:
        raise PermissionDenied("Only a school administrator in this school can review lesson notes.")


def _notify_reviewers(note, message):
    message = message[:300]
    recipients = SchoolMembership.objects.filter(
        school=note.subject.school,
        role=SchoolMembership.Role.SCHOOL_ADMIN,
        status=SchoolMembership.Status.ACTIVE,
    )
    LessonNoteNotification.objects.bulk_create(
        [LessonNoteNotification(lesson_note=note, recipient=recipient, message=message) for recipient in recipients]
    )
    notify_school_role(
        school=note.subject.school,
        role=SchoolMembership.Role.SCHOOL_ADMIN,
        kind=Notification.Kind.LESSON_REVIEW,
        title="Lesson note awaiting review",
        message=message,
        target_url=f"/dashboard/lesson-review/{note.id}/",
        deduplication_key=f"lesson:{note.id}:review:{note.current_version}:{note.status}",
    )


def _notify_author(note, message):
    message = message[:300]
    recipient = _author_membership(note)
    if recipient:
        LessonNoteNotification.objects.create(lesson_note=note, recipient=recipient, message=message)
        create_notification(
            recipient=recipient,
            kind=Notification.Kind.LESSON_REVIEW,
            title="Lesson note review update",
            message=message,
            target_url=f"/dashboard/lesson-notes/{note.id}/",
            deduplication_key=f"lesson:{note.id}:author:{note.current_version}:{note.status}",
        )


def _snapshot(note):
    data = {field: getattr(note, field) for field in SNAPSHOT_FIELDS}
    data.update({
        "subject_id": note.subject_id,
        "subject_name": note.subject.name,
        "week_ending": note.week_ending.isoformat(),
    })
    return data


def _create_version(note, actor, reason):
    note.current_version += 1
    note.save(update_fields=["current_version", "updated_at"])
    return LessonNoteVersion.objects.create(
        lesson_note=note,
        version_number=note.current_version,
        snapshot=_snapshot(note),
        reason=reason,
        created_by=actor,
    )


@transaction.atomic
def record_initial_lesson_version(*, note, actor):
    note = LessonNote.objects.select_for_update().select_related("subject").get(pk=note.pk)
    _require_author(note, actor)
    if note.current_version:
        return note.versions.get(version_number=note.current_version)
    return _create_version(note, actor, "Initial AI-generated draft")


@transaction.atomic
def revise_lesson_note(*, note, actor, values, reason):
    note = LessonNote.objects.select_for_update().select_related("subject").get(pk=note.pk)
    _require_author(note, actor)
    if note.status not in {LessonNote.Status.DRAFT, LessonNote.Status.SENT_BACK}:
        raise ValidationError("Only draft or returned lesson notes can be revised.")
    reason = reason.strip()
    if not reason:
        raise ValidationError("A revision reason is required.")
    for field, value in values.items():
        if field in LessonNote.EDITABLE_FIELDS or field == "subject":
            setattr(note, field, value)
    note.status = LessonNote.Status.DRAFT
    note.reviewed_by = None
    note.reviewed_at = None
    note.full_clean()
    note.save()
    version = _create_version(note, actor, reason)
    LessonNoteEvent.objects.create(
        lesson_note=note,
        event_type=LessonNoteEvent.EventType.REVISED,
        message=f"Created version {version.version_number}: {reason}",
        actor=actor,
    )
    return note


@transaction.atomic
def submit_lesson_note(*, note, actor, message=""):
    note = LessonNote.objects.select_for_update().select_related("subject").get(pk=note.pk)
    _require_author(note, actor)
    if note.status not in {LessonNote.Status.DRAFT, LessonNote.Status.SENT_BACK}:
        raise ValidationError("Only draft or returned lesson notes can be submitted.")
    if not note.current_version:
        _create_version(note, actor, "Initial draft submitted for review")
    note.status = LessonNote.Status.PENDING_REVIEW
    note.submitted_at = timezone.now()
    note.reviewed_by = None
    note.reviewed_at = None
    note.save(update_fields=["status", "submitted_at", "reviewed_by", "reviewed_at", "updated_at"])
    LessonNoteEvent.objects.create(
        lesson_note=note,
        event_type=LessonNoteEvent.EventType.SUBMITTED,
        message=message.strip(),
        actor=actor,
    )
    _notify_reviewers(note, f"{note.teacher.username} submitted {note.strand_topic} for review.")
    return note


@transaction.atomic
def review_lesson_note(*, note, actor, action, message=""):
    note = LessonNote.objects.select_for_update().select_related("subject", "teacher").get(pk=note.pk)
    _require_reviewer(note, actor)
    message = message.strip()
    if action == "reopen":
        if note.status != LessonNote.Status.APPROVED:
            raise ValidationError("Only approved lesson notes can be reopened.")
        if not message:
            raise ValidationError("A reason is required to reopen an approved lesson note.")
        note.status = LessonNote.Status.SENT_BACK
        note.reviewed_by = actor
        note.reviewed_at = timezone.now()
        note.save(
            allow_approved_reopen=True,
            update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"],
        )
        event_type = LessonNoteEvent.EventType.REOPENED
        notification = f"Your approved lesson note {note.strand_topic} was reopened: {message}"
    else:
        if note.status != LessonNote.Status.PENDING_REVIEW:
            raise ValidationError("Only pending lesson notes can be reviewed.")
        if action == "approve":
            note.status = LessonNote.Status.APPROVED
            event_type = LessonNoteEvent.EventType.APPROVED
            notification = f"Your lesson note {note.strand_topic} was approved."
        elif action == "return":
            if not message:
                raise ValidationError("A comment is required when sending a lesson note back.")
            note.status = LessonNote.Status.SENT_BACK
            event_type = LessonNoteEvent.EventType.SENT_BACK
            notification = f"Your lesson note {note.strand_topic} was sent back: {message}"
        else:
            raise ValidationError("Unknown review action.")
        note.reviewed_by = actor
        note.reviewed_at = timezone.now()
        note.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    LessonNoteEvent.objects.create(
        lesson_note=note, event_type=event_type, message=message, actor=actor
    )
    _notify_author(note, notification)
    return note


@transaction.atomic
def add_lesson_comment(*, note, actor, message):
    note = LessonNote.objects.select_for_update().select_related("subject", "teacher").get(pk=note.pk)
    is_author = actor.user_id == note.teacher_id and actor.role == SchoolMembership.Role.TEACHER
    is_reviewer = actor.role == SchoolMembership.Role.SCHOOL_ADMIN
    if actor.school_id != note.subject.school_id or not (is_author or is_reviewer):
        raise PermissionDenied("You cannot comment on this lesson note.")
    message = message.strip()
    if not message:
        raise ValidationError("Comment cannot be blank.")
    event = LessonNoteEvent.objects.create(
        lesson_note=note,
        event_type=LessonNoteEvent.EventType.COMMENT,
        message=message,
        actor=actor,
    )
    if is_author:
        _notify_reviewers(note, f"{note.teacher.username} commented on {note.strand_topic}: {message}")
    else:
        _notify_author(note, f"A reviewer commented on {note.strand_topic}: {message}")
    return event
