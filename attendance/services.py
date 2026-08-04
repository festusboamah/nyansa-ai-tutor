from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import ClassEnrollment, TeacherAssignment
from schools.models import SchoolMembership

from .models import (
    AttendanceRecord,
    AttendanceRevision,
    AttendanceSession,
    SchoolCalendarPolicy,
    SchoolClosure,
)


def instructional_dates(term, through=None):
    policy, _ = SchoolCalendarPolicy.objects.get_or_create(school=term.academic_year.school)
    end_date = min(term.end_date, through) if through else term.end_date
    if end_date < term.start_date:
        return []
    closed_dates = set()
    for closure in SchoolClosure.objects.filter(term=term, start_date__lte=end_date, end_date__gte=term.start_date):
        current = max(closure.start_date, term.start_date)
        closure_end = min(closure.end_date, end_date)
        while current <= closure_end:
            closed_dates.add(current)
            current += timedelta(days=1)
    dates = []
    current = term.start_date
    while current <= end_date:
        if current.weekday() in policy.weekday_set and current not in closed_dates:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def instructional_day_count(term, through=None):
    return len(instructional_dates(term, through=through))


def can_manage_class_attendance(actor, school_class, term):
    if actor.school_id != school_class.school_id or actor.status != SchoolMembership.Status.ACTIVE:
        return False
    if actor.role == SchoolMembership.Role.SCHOOL_ADMIN:
        return True
    if actor.role != SchoolMembership.Role.TEACHER:
        return False
    return school_class.class_teacher_id == actor.id or TeacherAssignment.objects.filter(
        teacher=actor,
        offering__school_class=school_class,
        offering__term=term,
    ).exists()


@transaction.atomic
def submit_attendance(*, school_class, term, attendance_date, actor, statuses, reasons=None):
    if not can_manage_class_attendance(actor, school_class, term):
        raise PermissionDenied("You are not assigned to manage attendance for this class.")
    if attendance_date not in set(instructional_dates(term)):
        raise ValidationError("Attendance can be submitted only for an instructional day.")
    roster = list(ClassEnrollment.objects.filter(
        school_class=school_class,
        status=ClassEnrollment.Status.ACTIVE,
        student__status=SchoolMembership.Status.ACTIVE,
    ).select_related("student"))
    roster_ids = {enrollment.student_id for enrollment in roster}
    normalized = {int(student_id): status for student_id, status in statuses.items()}
    normalized_reasons = {
        int(student_id): str(reason).strip()[:300]
        for student_id, reason in (reasons or {}).items()
    }
    if set(normalized) != roster_ids:
        raise ValidationError("Attendance must include every active student exactly once.")
    if any(status not in AttendanceRecord.Status.values for status in normalized.values()):
        raise ValidationError("Unknown attendance status.")
    session, _ = AttendanceSession.objects.select_for_update().get_or_create(
        school_class=school_class,
        attendance_date=attendance_date,
        defaults={
            "school": school_class.school,
            "term": term,
            "submitted_by": actor,
        },
    )
    if session.status == AttendanceSession.Status.SUBMITTED:
        raise ValidationError("This register is already submitted. Use the correction workflow.")
    session.school = school_class.school
    session.term = term
    session.submitted_by = actor
    session.status = AttendanceSession.Status.SUBMITTED
    session.submitted_at = timezone.now()
    session.full_clean()
    session.save()
    for enrollment in roster:
        record = AttendanceRecord(
            session=session,
            student=enrollment.student,
            status=normalized[enrollment.student_id],
            reason=(
                normalized_reasons.get(enrollment.student_id, "")
                if normalized[enrollment.student_id] != AttendanceRecord.Status.PRESENT
                else ""
            ),
            marked_by=actor,
        )
        record.full_clean()
        record.save()
    from communications.models import MessageTemplate
    from communications.models import Notification
    from communications.services import enqueue_guardian_event, notify_school_role

    for enrollment in roster:
        if normalized[enrollment.student_id] in {
            AttendanceRecord.Status.ABSENT, AttendanceRecord.Status.EXCUSED
        }:
            student = enrollment.student
            status_label = AttendanceRecord.Status(normalized[enrollment.student_id]).label.lower()
            enqueue_guardian_event(
                student=student,
                event_type=MessageTemplate.EventType.ATTENDANCE,
                business_reference=f"attendance:{session.pk}:student:{enrollment.student_id}",
                context={},
            )
            student_name = student.user.get_full_name() or student.user.username
            reason = normalized_reasons.get(enrollment.student_id, "")
            message = (
                f"{student_name} was marked {status_label} in {school_class.name} "
                f"on {attendance_date:%b. %d, %Y}."
            )
            if reason:
                message += f" Reason: {reason}"
            notify_school_role(
                school=school_class.school,
                role=SchoolMembership.Role.SCHOOL_ADMIN,
                kind=Notification.Kind.ATTENDANCE,
                title="Student attendance alert",
                message=message,
                target_url=(
                    f"/attendance/classes/{school_class.pk}/terms/{term.pk}/register/"
                    f"?date={attendance_date.isoformat()}"
                ),
                deduplication_key=f"attendance:{session.pk}:student:{student.pk}",
            )
    return session


@transaction.atomic
def correct_attendance(*, record, actor, new_status, reason):
    record = AttendanceRecord.objects.select_for_update().select_related(
        "session__school_class", "session__term"
    ).get(pk=record.pk)
    if not can_manage_class_attendance(actor, record.session.school_class, record.session.term):
        raise PermissionDenied("You cannot correct attendance for this class.")
    if record.session.status != AttendanceSession.Status.SUBMITTED:
        raise ValidationError("Only submitted attendance can be corrected.")
    reason = reason.strip()
    if not reason:
        raise ValidationError("A correction reason is required.")
    if new_status not in AttendanceRecord.Status.values:
        raise ValidationError("Unknown attendance status.")
    if new_status == record.status:
        raise ValidationError("Choose a different attendance status.")
    previous = record.status
    record.status = new_status
    record.marked_by = actor
    record.full_clean()
    record.save(update_fields=["status", "marked_by", "updated_at"])
    AttendanceRevision.objects.create(
        record=record,
        previous_status=previous,
        new_status=new_status,
        reason=reason,
        changed_by=actor,
    )
    return record


def student_attendance_summary(*, student, term, school_class=None, through=None):
    valid_dates = instructional_dates(term, through=through)
    days_open = len(valid_dates)
    records = AttendanceRecord.objects.filter(
        student=student,
        session__term=term,
        session__status=AttendanceSession.Status.SUBMITTED,
        session__attendance_date__in=valid_dates,
    )
    if school_class is not None:
        records = records.filter(session__school_class=school_class)
    counts = {status: records.filter(status=status).count() for status in AttendanceRecord.Status.values}
    percentage = None
    if days_open:
        percentage = min(
            Decimal("100.00"),
            (Decimal(counts[AttendanceRecord.Status.PRESENT]) / days_open * 100).quantize(Decimal("0.01")),
        )
    return {"days_open": days_open, "present": counts["PRESENT"], "absent": counts["ABSENT"], "excused": counts["EXCUSED"], "percentage": percentage}
