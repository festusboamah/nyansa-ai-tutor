"""Grade-boundary resolution. Sibling to evidence.py's read-only interface:
gradebook stays the single owner of both what counts as approved evidence
and how a score maps to a grade - other apps (e.g. reports) call in here
rather than querying GradeBoundary directly.
"""
from decimal import Decimal

from .models import GradeBoundary


def resolve_grade(percentage, *, scheme, subject=None):
    """Returns (grade, grade_point) for a 0-100 percentage against `scheme`'s
    configured GradeBoundary rows, or None if none are configured - the
    caller decides what fallback to use in that case. Subject-specific
    boundaries win over scheme-wide ones when both exist.
    """
    boundaries = GradeBoundary.objects.filter(scheme=scheme, subject=subject)
    if not boundaries.exists() and subject is not None:
        boundaries = GradeBoundary.objects.filter(scheme=scheme, subject__isnull=True)
    if not boundaries.exists():
        return None

    for boundary in boundaries.order_by("-minimum_mark"):
        minimum_percentage = boundary.minimum_mark / boundary.reference_max_mark * Decimal("100")
        if percentage >= minimum_percentage:
            return boundary.grade, boundary.grade_point
    return None
