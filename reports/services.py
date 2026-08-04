from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import ClassEnrollment, SubjectOffering, TeacherAssignment
from attendance.services import student_attendance_summary
from gradebook.models import GradeEntry, GradeScheme
from schools.models import SchoolMembership

from .models import ReportPolicy, ReportWorkflowEvent, TermReport


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
    entries = GradeEntry.objects.filter(
        student=student,
        assessment__offering=offering,
        assessment__category__scheme=scheme,
        status=GradeEntry.Status.PUBLISHED,
        review_status=GradeEntry.ReviewStatus.APPROVED,
    ).select_related("assessment__category")
    grouped = {}
    for entry in entries:
        grouped.setdefault(entry.assessment.category_id, []).append(entry.percentage)
    weighted, used_weight, categories = Decimal("0"), Decimal("0"), []
    for category in scheme.categories.all():
        values = grouped.get(category.pk, [])
        average = (sum(values, Decimal("0")) / len(values)) if values else None
        if average is not None:
            weighted += average * category.weight
            used_weight += category.weight
        categories.append({
            "name": category.name,
            "weight": str(category.weight),
            "average": str(average.quantize(Decimal("0.01"))) if average is not None else None,
        })
    score = (weighted / used_weight).quantize(Decimal("0.01")) if used_weight else None
    return {
        "subject": offering.subject.name,
        "score": str(score) if score is not None else None,
        "grade": "Pass" if score is not None and score >= pass_mark else ("Fail" if score is not None else "—"),
        "categories": categories,
    }


def build_snapshot(*, student, school_class, term, policy):
    school = school_class.school
    scheme = GradeScheme.objects.filter(
        school=school, academic_year=term.academic_year, status=GradeScheme.Status.ACTIVE
    ).prefetch_related("categories").first()
    if not scheme:
        raise ValidationError("Activate a grade scheme for this academic year before generating reports.")
    offerings = SubjectOffering.objects.filter(
        school_class=school_class, term=term
    ).select_related("subject").order_by("subject__name")
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
def update_report_details(*, report, actor, conduct, teacher_remark, promotion_outcome, administrator_remark=None):
    report = TermReport.objects.select_for_update().get(pk=report.pk)
    if not can_prepare_reports(actor, report.school_class, report.term):
        raise PermissionDenied("You cannot edit this report.")
    if report.status not in {TermReport.Status.DRAFT, TermReport.Status.RETURNED}:
        raise ValidationError("Only draft or returned reports can be edited.")
    report.conduct = conduct.strip()
    report.teacher_remark = teacher_remark.strip()
    if administrator_remark is not None:
        if actor.role != SchoolMembership.Role.SCHOOL_ADMIN:
            raise PermissionDenied("Only a school administrator can set the administrator remark.")
        report.administrator_remark = administrator_remark.strip()
    report.promotion_outcome = promotion_outcome
    report.save(update_fields=["conduct", "teacher_remark", "administrator_remark", "promotion_outcome", "updated_at"])
    return report


@transaction.atomic
def transition_report(*, report, actor, action, note=""):
    report = TermReport.objects.select_for_update().get(pk=report.pk)
    admin = actor.school_id == report.school_id and actor.is_active and actor.role == SchoolMembership.Role.SCHOOL_ADMIN
    transitions = {
        "submit": ({TermReport.Status.DRAFT, TermReport.Status.RETURNED}, TermReport.Status.PENDING),
        "approve": ({TermReport.Status.PENDING}, TermReport.Status.APPROVED),
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
