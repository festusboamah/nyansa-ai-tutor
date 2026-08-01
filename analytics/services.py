from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from academics.models import ClassEnrollment, TeacherAssignment
from attendance.models import AttendanceRecord, AttendanceSession
from attendance.services import instructional_day_count, student_attendance_summary
from gradebook.models import Assessment, GradeEntry
from reports.models import TermReport
from schools.models import SchoolMembership

from .models import EarlyWarningPolicy, Intervention, NarrativeSnapshot, RiskSignal


def can_view_class(actor, school_class, term):
    if actor.school_id != school_class.school_id or not actor.is_active:
        return False
    if actor.role == SchoolMembership.Role.SCHOOL_ADMIN:
        return True
    return actor.role == SchoolMembership.Role.TEACHER and (
        school_class.class_teacher_id == actor.id or TeacherAssignment.objects.filter(
            teacher=actor, offering__school_class=school_class, offering__term=term
        ).exists()
    )


def offering_metrics(offering):
    entries = GradeEntry.objects.filter(
        assessment__offering=offering, status=GradeEntry.Status.PUBLISHED,
        review_status=GradeEntry.ReviewStatus.APPROVED,
    )
    assessment_rows = []
    for assessment in Assessment.objects.filter(offering=offering).order_by("due_at", "id"):
        values = entries.filter(assessment=assessment)
        average = values.aggregate(value=Avg("score"))["value"]
        percentage = None
        if average is not None:
            percentage = (average / assessment.max_score * Decimal("100")).quantize(Decimal("0.01"))
        assessment_rows.append({
            "assessment": assessment.title, "average": percentage,
            "approved_entries": values.count(),
        })
    student_count = ClassEnrollment.objects.filter(
        school_class=offering.school_class, status=ClassEnrollment.Status.ACTIVE
    ).count()
    available = [row["average"] for row in assessment_rows if row["average"] is not None]
    latest = available[-1] if available else None
    previous = available[-2] if len(available) > 1 else None
    change = (latest - previous).quantize(Decimal("0.01")) if latest is not None and previous is not None else None
    return {
        "period": f"{offering.term.academic_year.name} · {offering.term.name}",
        "source": "Published, administrator-approved gradebook entries",
        "student_count": student_count, "assessments": assessment_rows,
        "latest_average": latest, "change_from_previous": change,
    }


def class_metrics(school_class, term):
    reports = TermReport.objects.filter(
        school_class=school_class, term=term, status=TermReport.Status.PUBLISHED,
        average_score__isnull=False,
    )
    academic_average = reports.aggregate(value=Avg("average_score"))["value"]
    roster = ClassEnrollment.objects.filter(
        school_class=school_class, status=ClassEnrollment.Status.ACTIVE
    ).select_related("student")
    days_open = instructional_day_count(term, through=term.end_date)
    attendance = AttendanceRecord.objects.filter(
        session__school_class=school_class, session__term=term,
        session__status=AttendanceSession.Status.SUBMITTED,
    )
    present = attendance.filter(status=AttendanceRecord.Status.PRESENT).count()
    possible = days_open * roster.count()
    attendance_percentage = (
        Decimal(present) / possible * 100
    ).quantize(Decimal("0.01")) if possible else None
    return {
        "period": f"{term.academic_year.name} · {term.name}",
        "academic_source": "Published term-report snapshots",
        "attendance_source": "Submitted attendance registers and derived instructional days",
        "student_count": roster.count(), "published_report_count": reports.count(),
        "academic_average": academic_average.quantize(Decimal("0.01")) if academic_average is not None else None,
        "attendance_percentage": attendance_percentage, "days_open": days_open,
    }


def school_metrics(school, term):
    classes = school.classes.filter(academic_year=term.academic_year)
    rows = [{"school_class": item, "metrics": class_metrics(item, term)} for item in classes]
    academic = [row["metrics"]["academic_average"] for row in rows if row["metrics"]["academic_average"] is not None]
    attendance = [row["metrics"]["attendance_percentage"] for row in rows if row["metrics"]["attendance_percentage"] is not None]
    return {
        "period": f"{term.academic_year.name} · {term.name}",
        "academic_source": "Published term-report snapshots",
        "attendance_source": "Submitted attendance registers and school calendars",
        "class_count": len(rows), "classes": rows,
        "academic_average": (sum(academic, Decimal("0")) / len(academic)).quantize(Decimal("0.01")) if academic else None,
        "attendance_percentage": (sum(attendance, Decimal("0")) / len(attendance)).quantize(Decimal("0.01")) if attendance else None,
    }


def _student_observation(policy, student, school_class, term):
    if policy.metric == EarlyWarningPolicy.Metric.LOW_AVERAGE:
        report = TermReport.objects.filter(
            student=student, school_class=school_class, term=term,
            status=TermReport.Status.PUBLISHED, average_score__isnull=False,
        ).first()
        if not report:
            return None
        return report.average_score, {
            "source": "Published term report", "report_id": report.id,
            "period": f"{term.academic_year.name} · {term.name}", "rule": "value below threshold",
        }
    if policy.metric == EarlyWarningPolicy.Metric.LOW_ATTENDANCE:
        summary = student_attendance_summary(
            student=student, term=term, school_class=school_class, through=term.end_date
        )
        if summary["percentage"] is None:
            return None
        return summary["percentage"], {
            "source": "Submitted attendance and derived instructional days",
            "period": f"{term.academic_year.name} · {term.name}",
            "present": summary["present"], "days_open": summary["days_open"], "rule": "value below threshold",
        }
    offerings = school_class.subject_offerings.filter(term=term)
    expected = Assessment.objects.filter(offering__in=offerings).count()
    approved = GradeEntry.objects.filter(
        student=student, assessment__offering__in=offerings,
        status=GradeEntry.Status.PUBLISHED, review_status=GradeEntry.ReviewStatus.APPROVED,
    ).count()
    missing = max(expected - approved, 0)
    return Decimal(missing), {
        "source": "Configured assessments and published approved grade entries",
        "period": f"{term.academic_year.name} · {term.name}",
        "expected": expected, "approved": approved, "rule": "value at or above threshold",
    }


@transaction.atomic
def generate_risk_signals(*, school_class, term, actor):
    if not can_view_class(actor, school_class, term):
        raise PermissionDenied("You cannot analyze this class.")
    policies = EarlyWarningPolicy.objects.filter(school=school_class.school, is_active=True)
    enrollments = ClassEnrollment.objects.filter(
        school_class=school_class, status=ClassEnrollment.Status.ACTIVE,
        student__status=SchoolMembership.Status.ACTIVE,
    ).select_related("student")
    active_keys, signals = set(), []
    for enrollment in enrollments:
        for policy in policies:
            observation = _student_observation(policy, enrollment.student, school_class, term)
            if observation is None:
                continue
            value, evidence = observation
            triggered = value >= policy.threshold if policy.metric == EarlyWarningPolicy.Metric.MISSING_GRADES else value < policy.threshold
            key = (policy.id, enrollment.student_id)
            if triggered:
                signal, _ = RiskSignal.objects.update_or_create(
                    policy=policy, student=enrollment.student, school_class=school_class, term=term,
                    defaults={"school": school_class.school, "observed_value": value, "evidence": evidence},
                )
                if signal.status == RiskSignal.Status.RESOLVED:
                    signal.status = RiskSignal.Status.OPEN
                    signal.resolved_by = None
                    signal.resolved_at = None
                    signal.save(update_fields=["status", "resolved_by", "resolved_at"])
                active_keys.add(key)
                signals.append(signal)
            else:
                RiskSignal.objects.filter(
                    policy=policy, student=enrollment.student, school_class=school_class, term=term,
                    status__in=[RiskSignal.Status.OPEN, RiskSignal.Status.ACKNOWLEDGED],
                ).update(status=RiskSignal.Status.RESOLVED, resolved_by=actor, resolved_at=timezone.now())
    return signals


@transaction.atomic
def create_intervention(*, signal, actor, owner, plan):
    if not can_view_class(actor, signal.school_class, signal.term):
        raise PermissionDenied("You cannot manage this signal.")
    plan = plan.strip()
    if not plan:
        raise ValidationError("An intervention plan is required.")
    if owner.school_id != signal.school_id or owner.role not in {
        SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN,
    }:
        raise ValidationError("Intervention owner must be school staff.")
    signal.status = RiskSignal.Status.ACKNOWLEDGED
    signal.acknowledged_by = actor
    signal.save(update_fields=["status", "acknowledged_by"])
    intervention = Intervention(signal=signal, owner=owner, plan=plan, created_by=actor)
    intervention.full_clean()
    intervention.save()
    return intervention


@transaction.atomic
def complete_intervention(*, intervention, actor, outcome):
    intervention = Intervention.objects.select_for_update().select_related(
        "signal__school_class", "signal__term"
    ).get(pk=intervention.pk)
    if not can_view_class(actor, intervention.signal.school_class, intervention.signal.term):
        raise PermissionDenied("You cannot complete this intervention.")
    outcome = outcome.strip()
    if not outcome:
        raise ValidationError("An intervention outcome is required.")
    intervention.status = Intervention.Status.COMPLETED
    intervention.outcome = outcome
    intervention.completed_at = timezone.now()
    intervention.save(update_fields=["status", "outcome", "completed_at", "updated_at"])
    if not intervention.signal.interventions.exclude(pk=intervention.pk).filter(
        status__in=[Intervention.Status.PLANNED, Intervention.Status.IN_PROGRESS]
    ).exists():
        intervention.signal.status = RiskSignal.Status.RESOLVED
        intervention.signal.resolved_by = actor
        intervention.signal.resolved_at = timezone.now()
        intervention.signal.save(update_fields=["status", "resolved_by", "resolved_at"])
    return intervention


def draft_narrative(metrics):
    academic = metrics.get("academic_average")
    attendance = metrics.get("attendance_percentage")
    parts = [f"Period: {metrics['period']}. Source records are listed with each metric."]
    parts.append(f"Academic average is {academic}%." if academic is not None else "No published academic average is available.")
    parts.append(f"Attendance is {attendance}%." if attendance is not None else "No attendance percentage is available.")
    parts.append("Review the underlying class rows and open warning signals before sharing this draft.")
    return " ".join(parts)


@transaction.atomic
def create_narrative(*, school, term, actor, scope, metrics, school_class=None, offering=None, generator=None):
    if actor.school_id != school.id or not actor.is_active:
        raise PermissionDenied("You cannot create this narrative.")
    safe_metrics = _json_safe(metrics)
    method = "grounded-template"
    selected_generator = generator
    if selected_generator is None and settings.ANALYTICS_AI_NARRATIVES:
        from .narrative_ai import generate_ai_narrative
        selected_generator = generate_ai_narrative
        method = f"claude:{settings.ANALYTICS_AI_MODEL}"
    elif selected_generator is not None:
        method = "injected-assisted-generator"
    narrative = (selected_generator or draft_narrative)(safe_metrics)
    item = NarrativeSnapshot(
        school=school, term=term, scope=scope, school_class=school_class, offering=offering,
        metrics_snapshot=safe_metrics, narrative=narrative, generated_by=actor,
        generation_method=method,
    )
    item.full_clean()
    item.save()
    return item


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items() if key != "school_class"}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


@transaction.atomic
def approve_narrative(*, narrative, actor):
    if actor.school_id != narrative.school_id or actor.role != SchoolMembership.Role.SCHOOL_ADMIN:
        raise PermissionDenied("Only a school administrator can approve a narrative.")
    narrative = NarrativeSnapshot.objects.select_for_update().get(pk=narrative.pk)
    narrative.status = NarrativeSnapshot.Status.APPROVED
    narrative.reviewed_by = actor
    narrative.reviewed_at = timezone.now()
    narrative.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    return narrative
