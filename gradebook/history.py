from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from schools.models import SchoolMembership

from .models import GradeEntry, GradeEntryRevision, GradeReviewDecision


@transaction.atomic
def record_grade_entry(
    *, school, assessment, student, actor, score, source, status, reason, change_type=None
):
    reason = reason.strip()
    if not reason:
        raise ValidationError("A reason is required for every grade change.")
    if actor.school_id != school.id or actor.role not in {
        SchoolMembership.Role.TEACHER,
        SchoolMembership.Role.SCHOOL_ADMIN,
    }:
        raise PermissionDenied("Grade recorder must belong to the same school.")
    entry = GradeEntry.objects.select_for_update().filter(
        assessment=assessment, student=student
    ).first()
    created = entry is None
    if created:
        entry = GradeEntry(school=school, assessment=assessment, student=student)
        previous_score = None
        previous_status = ""
        previous_source = ""
    else:
        previous_score = entry.score
        previous_status = entry.status
        previous_source = entry.source
        if entry.review_status == GradeEntry.ReviewStatus.APPROVED and (
            entry.score != score or entry.status != status or entry.source != source
        ):
            raise ValidationError("Approved grades must be returned by an administrator before correction.")

    changed = created or entry.score != score or entry.status != status or entry.source != source
    if not changed:
        return entry, False
    entry.score = score
    entry.source = source
    entry.status = status
    entry.recorded_by = actor
    entry.review_status = (
        GradeEntry.ReviewStatus.PENDING
        if status == GradeEntry.Status.PUBLISHED
        else GradeEntry.ReviewStatus.NOT_REVIEWED
    )
    entry.reviewed_by = None
    entry.reviewed_at = None
    entry.review_note = ""
    entry.full_clean()
    entry.save()

    if change_type is None:
        if source == GradeEntry.Source.IMPORT:
            change_type = GradeEntryRevision.ChangeType.IMPORTED
        elif source == GradeEntry.Source.ONLINE:
            change_type = GradeEntryRevision.ChangeType.SYNCED
        elif created:
            change_type = GradeEntryRevision.ChangeType.CREATED
        else:
            change_type = GradeEntryRevision.ChangeType.CORRECTED
    GradeEntryRevision.objects.create(
        entry=entry,
        change_type=change_type,
        previous_score=previous_score,
        new_score=entry.score,
        previous_status=previous_status,
        new_status=entry.status,
        previous_source=previous_source,
        new_source=entry.source,
        reason=reason,
        changed_by=actor,
    )
    return entry, True


@transaction.atomic
def review_grade_entry(*, entry, reviewer, decision, note=""):
    entry = GradeEntry.objects.select_for_update().get(pk=entry.pk)
    if reviewer.school_id != entry.school_id or reviewer.role != SchoolMembership.Role.SCHOOL_ADMIN:
        raise PermissionDenied("Only a school administrator in this school can review grades.")
    if entry.status != GradeEntry.Status.PUBLISHED:
        raise ValidationError("Only published grades can be reviewed.")
    if decision not in GradeReviewDecision.Decision.values:
        raise ValidationError("Unknown review decision.")
    if entry.review_status == decision:
        raise ValidationError(f"This grade is already {decision.lower()}.")
    note = note.strip()
    if decision == GradeReviewDecision.Decision.RETURNED and not note:
        raise ValidationError("A note is required when returning a grade.")
    entry.review_status = decision
    entry.reviewed_by = reviewer
    entry.reviewed_at = timezone.now()
    entry.review_note = note
    entry.full_clean()
    entry.save(update_fields=["review_status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
    GradeReviewDecision.objects.create(
        entry=entry, decision=decision, note=note, reviewed_by=reviewer
    )
    return entry
