from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg

from academics.models import ClassEnrollment
from quizzes.models import AssignmentSubmission, Submission
from schools.models import SchoolMembership

from .history import record_grade_entry
from .models import GradeEntry, GradeEntryRevision


def _active_students(assessment):
    memberships = SchoolMembership.objects.filter(
        school=assessment.school,
        role=SchoolMembership.Role.STUDENT,
        status=SchoolMembership.Status.ACTIVE,
        class_enrollments__school_class=assessment.offering.school_class,
        class_enrollments__status=ClassEnrollment.Status.ACTIVE,
    ).select_related("user").distinct()
    return {membership.user_id: membership for membership in memberships}


@transaction.atomic
def sync_legacy_assessment(*, assessment, actor):
    if assessment.status == assessment.Status.CLOSED:
        raise ValidationError("Closed assessments cannot be synchronized.")
    students = _active_students(assessment)
    results = []
    source_label = ""
    if assessment.legacy_quiz_id:
        source_label = f"quiz '{assessment.legacy_quiz.title}'"
        averages = Submission.objects.filter(
            quiz=assessment.legacy_quiz,
            student_id__in=students,
            score__isnull=False,
        ).values("student_id").annotate(average_score=Avg("score"))
        for result in averages:
            normalized = Decimal(str(result["average_score"])) * assessment.max_score / Decimal("100")
            results.append((students[result["student_id"]], normalized.quantize(Decimal("0.01"))))
    elif assessment.legacy_assignment_id:
        source_label = f"assignment '{assessment.legacy_assignment.title}'"
        submissions = AssignmentSubmission.objects.filter(
            assignment=assessment.legacy_assignment,
            student_id__in=students,
            final_score__isnull=False,
        ).order_by("student_id", "-graded_at", "-submitted_at", "-id")
        seen = set()
        for submission in submissions:
            if submission.student_id in seen:
                continue
            seen.add(submission.student_id)
            if not submission.max_score or submission.max_score <= 0:
                raise ValidationError(f"Submission {submission.pk} has an invalid maximum score.")
            normalized = (
                Decimal(str(submission.final_score))
                / Decimal(str(submission.max_score))
                * assessment.max_score
            )
            results.append((students[submission.student_id], normalized.quantize(Decimal("0.01"))))
    else:
        raise ValidationError("Link this assessment to a legacy quiz or assignment before synchronization.")

    changed = 0
    unchanged = 0
    for student, score in results:
        _, was_changed = record_grade_entry(
            school=assessment.school,
            assessment=assessment,
            student=student,
            actor=actor,
            score=score,
            source=GradeEntry.Source.ONLINE,
            status=GradeEntry.Status.PUBLISHED,
            reason=f"Synchronized from legacy {source_label}.",
            change_type=GradeEntryRevision.ChangeType.SYNCED,
        )
        changed += int(was_changed)
        unchanged += int(not was_changed)
    return {"source": source_label, "found": len(results), "changed": changed, "unchanged": unchanged}
