from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction

from .models import AssessmentCategory, GradeEntry, GradeScheme


@transaction.atomic
def ensure_default_grade_scheme(academic_year):
    active = GradeScheme.objects.filter(
        school=academic_year.school,
        academic_year=academic_year,
        status=GradeScheme.Status.ACTIVE,
    ).prefetch_related("categories").first()
    if active:
        return active
    scheme, _ = GradeScheme.objects.get_or_create(
        school=academic_year.school,
        academic_year=academic_year,
        name="Standard grading scheme",
        defaults={"status": GradeScheme.Status.ACTIVE},
    )
    AssessmentCategory.objects.get_or_create(
        scheme=scheme,
        code="continuous-assessment",
        defaults={"name": "Continuous assessment", "weight": Decimal("50.00"), "order": 1},
    )
    AssessmentCategory.objects.get_or_create(
        scheme=scheme,
        code="end-of-term",
        defaults={"name": "End-of-term assessment", "weight": Decimal("50.00"), "order": 2},
    )
    if scheme.status != GradeScheme.Status.ACTIVE:
        scheme.status = GradeScheme.Status.ACTIVE
        scheme.save(update_fields=["status", "updated_at"])
    return scheme


@transaction.atomic
def activate_grade_scheme(scheme):
    scheme = GradeScheme.objects.select_for_update().get(pk=scheme.pk)
    total = scheme.categories.aggregate(total_weight=models.Sum("weight"))["total_weight"]
    if total is None:
        raise ValidationError("A grade scheme must have at least one category before activation.")
    if total != Decimal("100.00"):
        raise ValidationError(f"Category weights must total 100.00%; current total is {total}%.")
    GradeScheme.objects.filter(
        school=scheme.school,
        academic_year=scheme.academic_year,
        status=GradeScheme.Status.ACTIVE,
    ).exclude(pk=scheme.pk).update(status=GradeScheme.Status.ARCHIVED)
    scheme.status = GradeScheme.Status.ACTIVE
    scheme.save(update_fields=["status", "updated_at"])
    return scheme


def calculate_weighted_result(*, student, offering, scheme):
    if student.school_id != offering.school_id or scheme.school_id != offering.school_id:
        raise ValidationError("Student, offering, and grade scheme must belong to the same school.")
    if scheme.academic_year_id != offering.term.academic_year_id:
        raise ValidationError("Grade scheme must belong to the offering's academic year.")

    entries = GradeEntry.objects.filter(
        student=student,
        assessment__offering=offering,
        assessment__category__scheme=scheme,
        status=GradeEntry.Status.PUBLISHED,
    ).select_related("assessment__category")
    scores_by_category = {}
    for entry in entries:
        scores_by_category.setdefault(entry.assessment.category_id, []).append(entry.percentage)

    breakdown = []
    weighted_points = Decimal("0")
    used_weight = Decimal("0")
    for category in scheme.categories.all():
        percentages = scores_by_category.get(category.pk, [])
        average = None
        if percentages:
            average = sum(percentages, Decimal("0")) / len(percentages)
            weighted_points += average * category.weight
            used_weight += category.weight
        breakdown.append(
            {"category": category, "average": average.quantize(Decimal("0.01")) if average is not None else None}
        )

    final_score = None
    if used_weight:
        final_score = (weighted_points / used_weight).quantize(Decimal("0.01"))
    return {"categories": breakdown, "final_score": final_score, "used_weight": used_weight}
