from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import ClassEnrollment, SubjectOffering, TeacherAssignment
from attendance.services import student_attendance_summary
from gradebook.evidence import active_scheme_for, category_evidence
from schools.models import SchoolMembership

from .models import ReportPolicy, ReportWorkflowEvent, TermReport


CORE_SUBJECT_ORDER = {
    "social studies": 0,
    "english language": 1,
    "mathematics": 2,
    "science": 3,
}
REPORT_EXCLUDED_SUBJECTS = {"physical education", "physical and health education"}


def report_subject_sort_key(subject_name):
    normalised = subject_name.strip().casefold()
    return CORE_SUBJECT_ORDER.get(normalised, len(CORE_SUBJECT_ORDER)), normalised


def _ges_grade(score):
    if score is None:
        return "—", "No approved score"
    boundaries = (
        (Decimal("90"), "1", "Highest"),
        (Decimal("80"), "2", "Higher"),
        (Decimal("70"), "3", "High"),
        (Decimal("60"), "4", "High Average"),
        (Decimal("55"), "5", "Average"),
        (Decimal("50"), "6", "Low Average"),
        (Decimal("40"), "7", "Low"),
        (Decimal("30"), "8", "Lowest"),
        (Decimal("0"), "9", "Fail"),
    )
    return next((grade, remark) for minimum, grade, remark in boundaries if score >= minimum)


def can_prepare_reports(actor, school_class, term):
    if actor.school_id != school_class.school_id or not actor.is_active:
        return False
    if actor.role == SchoolMembership.Role.SCHOOL_ADMIN:
        return True
    if actor.role != SchoolMembership.Role.TEACHER:
        return False
    return school_class.class_teacher_id == actor.id or TeacherAssignment.objects.filter(
        teacher=actor, offering__school_class=school_class, offering__term=term
    ).exists()


def _subject_result(student, offering, scheme, pass_mark):
    weighted, categories = Decimal("0"), []
    class_score = exam_score = None
    for row in category_evidence(student, offering, scheme):
        average = row["average"]
        contribution = None
        if average is not None:
            weighted += average * row["weight"]
            contribution = (average * row["weight"] / Decimal("100")).quantize(Decimal("0.01"))
            category_key = f"{row['code']} {row['name']}".lower()
            if any(label in category_key for label in ("continuous", "class score", "term work")):
                class_score = contribution
            elif any(label in category_key for label in ("end-of-term", "exam")):
                exam_score = contribution
        categories.append({
            "name": row["name"],
            "weight": str(row["weight"]),
            "average": str(average.quantize(Decimal("0.01"))) if average is not None else None,
            "contribution": str(contribution) if contribution is not None else None,
        })
    complete = bool(categories) and all(item["average"] is not None for item in categories)
    score = (weighted / Decimal("100")).quantize(Decimal("0.01")) if complete else None
    grade, remark = _ges_grade(score)
    return {
        "subject": offering.subject.name,
        "score": str(score) if score is not None else None,
        "class_score": str(class_score) if class_score is not None else None,
        "exam_score": str(exam_score) if exam_score is not None else None,
        "categories": categories,
        "grade": grade,
        "remark": remark,
    }


def build_snapshot(*, student, school_class, term, policy):
    school = school_class.school
    scheme = active_scheme_for(school, term.academic_year)
    if not scheme:
        raise ValidationError("Activate a grade scheme for this academic year before generating reports.")
    offerings = list(SubjectOffering.objects.filter(
        school_class=school_class, term=term
    ).select_related("subject"))
    offerings = [
        offering for offering in offerings
        if offering.subject.name.strip().casefold() not in REPORT_EXCLUDED_SUBJECTS
    ]
    offerings.sort(key=lambda offering: report_subject_sort_key(offering.subject.name))
    subjects = [_subject_result(student, offering, scheme, policy.pass_mark) for offering in offerings]
    scored = [Decimal(item["score"]) for item in subjects if item["score"] is not None]
    total = sum(scored, Decimal("0"))
    average = (total / len(scored)).quantize(Decimal("0.01")) if scored else None
    attendance = student_attendance_summary(
        student=student, term=term, school_class=school_class, through=term.end_date
    )
    previous_term = term.academic_year.terms.filter(order__lt=term.order).order_by("-order").first()
    previous_report = None
    if previous_term:
        previous_report = TermReport.objects.filter(
            school_class=school_class, term=previous_term, student=student,
            status=TermReport.Status.PUBLISHED,
        ).first()
    comparison = None
    if previous_report and previous_report.average_score is not None and average is not None:
        comparison = {
            "term": previous_term.name,
            "average": str(previous_report.average_score),
            "change": str((average - previous_report.average_score).quantize(Decimal("0.01"))),
        }
    profile = getattr(student, "student_profile", None)
    age = None
    if profile and profile.date_of_birth:
        on_date = term.end_date
        age = on_date.year - profile.date_of_birth.year - (
            (on_date.month, on_date.day) < (profile.date_of_birth.month, profile.date_of_birth.day)
        )
    return {
        "school": {"name": school.name, "address": school.address, "phone": school.phone, "email": school.email},
        "academic_year": term.academic_year.name,
        "term": term.name,
        "class": school_class.name,
        "class_teacher": (
            school_class.class_teacher.user.get_full_name() or school_class.class_teacher.user.username
            if school_class.class_teacher_id else ""
        ),
        "student": {
            "name": student.user.get_full_name() or student.user.username,
            "identifier": student.identifier,
            "gender": profile.get_gender_display() if profile and profile.gender else "",
            "date_of_birth": profile.date_of_birth.isoformat() if profile and profile.date_of_birth else "",
            "age": age,
        },
        "policy": {
            "show_position": policy.show_position,
            "pass_mark": str(policy.pass_mark),
            "promotion_average": str(policy.promotion_average),
        },
        "subjects": subjects,
        "attendance": {
            key: str(value) if isinstance(value, Decimal) else value for key, value in attendance.items()
        },
        "prior_term": comparison,
        "total": str(total.quantize(Decimal("0.01"))),
        "average": str(average) if average is not None else None,
        "generated_at": timezone.now().isoformat(),
    }, total, average


@transaction.atomic
def generate_class_reports(*, school_class, term, actor):
    if not can_prepare_reports(actor, school_class, term):
        raise PermissionDenied("You cannot prepare reports for this class.")
    policy, _ = ReportPolicy.objects.get_or_create(
        school=school_class.school, academic_year=term.academic_year
    )
    enrollments = list(ClassEnrollment.objects.filter(
        school_class=school_class, status=ClassEnrollment.Status.ACTIVE,
        student__status=SchoolMembership.Status.ACTIVE,
    ).select_related("student__user"))
    reports = []
    for enrollment in enrollments:
        report = TermReport.objects.select_for_update().filter(
            school_class=school_class, term=term, student=enrollment.student
        ).first()
        if report and report.status not in {TermReport.Status.DRAFT, TermReport.Status.RETURNED}:
            reports.append(report)
            continue
        snapshot, total, average = build_snapshot(
            student=enrollment.student, school_class=school_class, term=term, policy=policy
        )
        if report is None:
            report = TermReport(
                school=school_class.school, school_class=school_class, term=term,
                student=enrollment.student, prepared_by=actor,
            )
        report.snapshot = snapshot
        report.total_score = total
        report.average_score = average
        report.prepared_by = actor
        if not report.teacher_remark and average is not None:
            report.teacher_remark = (
                "A strong term. Keep building on this progress."
                if average >= policy.promotion_average else
                "More consistent practice and support will strengthen progress."
            )
        if report.promotion_outcome == TermReport.Promotion.PENDING and average is not None:
            report.promotion_outcome = (
                TermReport.Promotion.PROMOTED if average >= policy.promotion_average
                else TermReport.Promotion.REPEATED
            )
        report.full_clean()
        report.save()
        ReportWorkflowEvent.objects.create(
            report=report, action=ReportWorkflowEvent.Action.GENERATED,
            from_status=report.status, to_status=report.status,
            note="Snapshot generated from approved grades and attendance.", actor=actor,
        )
        reports.append(report)
    ranked = sorted([item for item in reports if item.average_score is not None], key=lambda x: x.average_score, reverse=True)
    if policy.show_position:
        last_score, last_position = None, 0
        for index, report in enumerate(ranked, 1):
            if report.average_score != last_score:
                last_position = index
                last_score = report.average_score
            if report.status in {TermReport.Status.DRAFT, TermReport.Status.RETURNED}:
                report.position = last_position
                report.snapshot["position"] = last_position
                report.save(update_fields=["position", "snapshot", "updated_at"])
    return reports


@transaction.atomic
def update_report_details(
    *, report, actor, conduct=None, teacher_remark=None,
    promotion_outcome=None, administrator_remark=None,
):
    report = TermReport.objects.select_for_update().get(pk=report.pk)
    if not can_prepare_reports(actor, report.school_class, report.term):
        raise PermissionDenied("You cannot edit this report.")
    editable_statuses = {TermReport.Status.DRAFT, TermReport.Status.RETURNED}
    if actor.role == SchoolMembership.Role.SCHOOL_ADMIN:
        editable_statuses |= {TermReport.Status.PENDING, TermReport.Status.APPROVED}
    if report.status not in editable_statuses:
        raise ValidationError("This report can no longer be edited at its current workflow stage.")
    if actor.role == SchoolMembership.Role.SCHOOL_ADMIN:
        if administrator_remark is not None:
            report.administrator_remark = administrator_remark.strip()
        if promotion_outcome is not None:
            report.promotion_outcome = promotion_outcome
    else:
        if conduct is not None:
            report.conduct = conduct.strip()
        if teacher_remark is not None:
            report.teacher_remark = teacher_remark.strip()
    report.save(update_fields=[
        "conduct", "teacher_remark", "administrator_remark", "promotion_outcome", "updated_at"
    ])
    return report


@transaction.atomic
def transition_report(*, report, actor, action, note=""):
    report = TermReport.objects.select_for_update().get(pk=report.pk)
    admin = actor.school_id == report.school_id and actor.is_active and actor.role == SchoolMembership.Role.SCHOOL_ADMIN
    transitions = {
        "submit": ({TermReport.Status.DRAFT, TermReport.Status.RETURNED}, TermReport.Status.PENDING),
        "approve": ({TermReport.Status.DRAFT, TermReport.Status.RETURNED, TermReport.Status.PENDING}, TermReport.Status.APPROVED),
        "return": ({TermReport.Status.PENDING}, TermReport.Status.RETURNED),
        "publish": ({TermReport.Status.APPROVED}, TermReport.Status.PUBLISHED),
        "reopen": ({TermReport.Status.PUBLISHED}, TermReport.Status.DRAFT),
    }
    if action not in transitions:
        raise ValidationError("Unknown report action.")
    allowed, target = transitions[action]
    if report.status not in allowed:
        raise ValidationError(f"A {report.get_status_display().lower()} report cannot be {action}ed.")
    if action == "submit":
        if actor.role != SchoolMembership.Role.TEACHER:
            raise PermissionDenied("Only a teacher can submit a report for review.")
        if not can_prepare_reports(actor, report.school_class, report.term):
            raise PermissionDenied("You cannot submit this report.")
    elif not admin:
        raise PermissionDenied("Only a school administrator can perform this action.")
    if action in {"return", "reopen"} and not note.strip():
        raise ValidationError("A reason is required.")
    previous = report.status
    now = timezone.now()
    report.status = target
    if action == "submit": report.submitted_at = now
    if action in {"approve", "return"}: report.reviewed_by, report.reviewed_at = actor, now
    if action == "publish": report.published_at = now
    if action == "reopen":
        report.version += 1
        report.published_at = None
    report.save()
    event_actions = {
        "submit": ReportWorkflowEvent.Action.SUBMITTED,
        "approve": ReportWorkflowEvent.Action.APPROVED,
        "return": ReportWorkflowEvent.Action.RETURNED,
        "publish": ReportWorkflowEvent.Action.PUBLISHED,
        "reopen": ReportWorkflowEvent.Action.REOPENED,
    }
    ReportWorkflowEvent.objects.create(
        report=report, action=event_actions[action], from_status=previous,
        to_status=target, note=note.strip(), actor=actor,
    )
    from communications.models import Notification
    from communications.services import create_notification, notify_school_role

    # Dashboard links remain valid even when disposable demo records are reseeded.
    report_url = "/reports/"
    if action == "submit":
        notify_school_role(
            school=report.school,
            role=SchoolMembership.Role.SCHOOL_ADMIN,
            kind=Notification.Kind.REPORT_REVIEW,
            title="Term report awaiting review",
            message=f"A report for {report.student.user.get_full_name() or report.student.user.username} was submitted.",
            target_url=report_url,
            deduplication_key=f"report:{report.id}:submitted:v{report.version}",
        )
    elif action in {"approve", "return", "publish", "reopen"}:
        create_notification(
            recipient=report.prepared_by,
            kind=Notification.Kind.REPORT_REVIEW,
            title="Term report updated",
            message=f"The report for {report.student.user.get_full_name() or report.student.user.username} was {target.lower()}." + (f" {note.strip()}" if note.strip() else ""),
            target_url=report_url,
            deduplication_key=f"report:{report.id}:{action}:v{report.version}",
        )
    if action == "publish":
        from communications.models import MessageTemplate
        from communications.services import enqueue_guardian_event

        enqueue_guardian_event(
            student=report.student,
            event_type=MessageTemplate.EventType.REPORT,
            business_reference=f"term-report:{report.pk}:version:{report.version}",
            context={},
        )
    return report
