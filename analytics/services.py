from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from academics.models import ClassEnrollment, TeacherAssignment
from ai_core.client import AIError
from courses.models import Subject
from gradebook.models import Assessment, GradeEntry
from mastery.services import class_topic_bands
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


def _percentage_average(entries):
    """Normalizes each GradeEntry's score against its own assessment's max_score,
    then averages those percentages so entries from differently-scaled assessments
    are comparable."""
    values = list(entries.values_list("score", "assessment__max_score"))
    percentages = [score / max_score * Decimal("100") for score, max_score in values if max_score]
    if not percentages:
        return None, 0
    average = (sum(percentages, Decimal("0")) / len(percentages)).quantize(Decimal("0.01"))
    return average, len(percentages)


def class_metrics(school_class, term):
    offerings = school_class.subject_offerings.filter(term=term)
    approved_entries = GradeEntry.objects.filter(
        assessment__offering__in=offerings, status=GradeEntry.Status.PUBLISHED,
        review_status=GradeEntry.ReviewStatus.APPROVED,
    )
    academic_average, evaluated_entry_count = _percentage_average(approved_entries)

    roster_student_ids = list(ClassEnrollment.objects.filter(
        school_class=school_class, status=ClassEnrollment.Status.ACTIVE
    ).values_list("student_id", flat=True))
    expected_assessments = Assessment.objects.filter(offering__in=offerings).count()
    possible = expected_assessments * len(roster_student_ids)
    recorded = GradeEntry.objects.filter(
        assessment__offering__in=offerings, student_id__in=roster_student_ids,
    ).count()
    submission_rate = (
        Decimal(recorded) / possible * 100
    ).quantize(Decimal("0.01")) if possible else None

    return {
        "period": f"{term.academic_year.name} · {term.name}",
        "academic_source": "Published, administrator-approved gradebook entries",
        "submission_source": "Recorded grade entries against configured assessments",
        "student_count": len(roster_student_ids), "evaluated_entry_count": evaluated_entry_count,
        "academic_average": academic_average,
        "submission_rate": submission_rate, "expected_assessments": expected_assessments,
    }


def class_insight_metrics(school_class, term):
    metrics = dict(class_metrics(school_class, term))
    subjects = Subject.objects.filter(
        school=school_class.school, offerings__school_class=school_class, offerings__term=term
    ).distinct()
    topics_needing_support = []
    for subject in subjects:
        for row in class_topic_bands(school_class, subject, term):
            needs_support_count = row["counts"]["NEEDS_SUPPORT"]
            if needs_support_count > 0:
                topics_needing_support.append({
                    "subject": subject.name,
                    "strand": row["strand"].name,
                    "topic": row["topic"].name,
                    "needs_support_count": needs_support_count,
                    "mastered_count": row["counts"]["MASTERED"],
                })
    metrics["topics_needing_support"] = topics_needing_support
    return metrics


def school_metrics(school, term):
    classes = school.classes.filter(academic_year=term.academic_year)
    rows = [{"school_class": item, "metrics": class_metrics(item, term)} for item in classes]
    academic = [row["metrics"]["academic_average"] for row in rows if row["metrics"]["academic_average"] is not None]
    submission = [row["metrics"]["submission_rate"] for row in rows if row["metrics"]["submission_rate"] is not None]
    return {
        "period": f"{term.academic_year.name} · {term.name}",
        "academic_source": "Published, administrator-approved gradebook entries",
        "submission_source": "Recorded grade entries against configured assessments",
        "class_count": len(rows), "classes": rows,
        "academic_average": (sum(academic, Decimal("0")) / len(academic)).quantize(Decimal("0.01")) if academic else None,
        "submission_rate": (sum(submission, Decimal("0")) / len(submission)).quantize(Decimal("0.01")) if submission else None,
    }


def _student_observation(policy, student, school_class, term):
    offerings = school_class.subject_offerings.filter(term=term)
    period = f"{term.academic_year.name} · {term.name}"

    if policy.metric == EarlyWarningPolicy.Metric.LOW_AVERAGE:
        entries = GradeEntry.objects.filter(
            student=student, assessment__offering__in=offerings,
            status=GradeEntry.Status.PUBLISHED, review_status=GradeEntry.ReviewStatus.APPROVED,
        )
        average, entry_count = _percentage_average(entries)
        if average is None:
            return None
        return average, {
            "source": "Published, administrator-approved gradebook entries",
            "period": period, "entry_count": entry_count, "rule": "value below threshold",
        }
    if policy.metric == EarlyWarningPolicy.Metric.LOW_SUBMISSION_RATE:
        expected = Assessment.objects.filter(offering__in=offerings).count()
        if expected == 0:
            return None
        recorded = GradeEntry.objects.filter(student=student, assessment__offering__in=offerings).count()
        percentage = (Decimal(recorded) / expected * 100).quantize(Decimal("0.01"))
        return percentage, {
            "source": "Recorded grade entries against configured assessments",
            "period": period, "recorded": recorded, "expected": expected, "rule": "value below threshold",
        }
    expected = Assessment.objects.filter(offering__in=offerings).count()
    approved = GradeEntry.objects.filter(
        student=student, assessment__offering__in=offerings,
        status=GradeEntry.Status.PUBLISHED, review_status=GradeEntry.ReviewStatus.APPROVED,
    ).count()
    missing = max(expected - approved, 0)
    return Decimal(missing), {
        "source": "Configured assessments and published approved grade entries",
        "period": period, "expected": expected, "approved": approved, "rule": "value at or above threshold",
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
    submission = metrics.get("submission_rate")
    parts = [f"Period: {metrics['period']}. Source records are listed with each metric."]
    parts.append(f"Academic average is {academic}%." if academic is not None else "No academic average is available from approved gradebook entries.")
    parts.append(f"Submission rate is {submission}%." if submission is not None else "No submission rate is available.")
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
        from functools import partial

        from .narrative_ai import generate_ai_narrative
        selected_generator = partial(generate_ai_narrative, school=school)
        method = f"claude:{settings.ANALYTICS_AI_MODEL}"
    elif selected_generator is not None:
        method = "injected-assisted-generator"

    if selected_generator is not None:
        try:
            narrative = selected_generator(safe_metrics)
        except AIError:
            narrative = draft_narrative(safe_metrics)
            method = "grounded-template"
    else:
        narrative = draft_narrative(safe_metrics)
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
