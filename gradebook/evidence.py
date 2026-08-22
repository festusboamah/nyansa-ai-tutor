"""Read-only approved-evidence interface for consumers outside gradebook.

Other apps (e.g. `reports`) should call these functions instead of querying
`GradeEntry`/`GradeScheme` directly, so gradebook stays the single owner of
what counts as approved grading evidence.
"""
from decimal import Decimal

from .models import GradeEntry, GradeScheme


def active_scheme_for(school, academic_year):
    """The school's active GradeScheme for an academic year, or None."""
    return GradeScheme.objects.filter(
        school=school, academic_year=academic_year, status=GradeScheme.Status.ACTIVE
    ).prefetch_related("categories").first()


def approved_evidence_for_school(school, term):
    """Every published+approved GradeEntry for a school in a term - the bulk,
    consumer-facing counterpart to `category_evidence`'s per-student rows."""
    return GradeEntry.objects.filter(
        school=school, assessment__offering__term=term,
        status=GradeEntry.Status.PUBLISHED, review_status=GradeEntry.ReviewStatus.APPROVED,
    ).select_related("student__user", "assessment__topic", "assessment__offering__subject")


def category_evidence(student, offering, scheme):
    """
    One row per category in `scheme`, with the student's published+approved
    GradeEntry evidence for `offering` in that category:
    {category_id, name, code, weight, average, entry_count}.
    """
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

    rows = []
    for category in scheme.categories.all():
        values = grouped.get(category.pk, [])
        average = (sum(values, Decimal("0")) / len(values)) if values else None
        rows.append({
            "category_id": category.pk,
            "name": category.name,
            "code": category.code,
            "weight": category.weight,
            "average": average,
            "entry_count": len(values),
        })
    return rows
