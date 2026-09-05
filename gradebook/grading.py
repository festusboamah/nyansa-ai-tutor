"""Grade-boundary resolution. Sibling to evidence.py's read-only interface:
gradebook stays the single owner of both what counts as approved evidence
and how a score maps to a grade - other apps (e.g. reports) call in here
rather than querying GradeBoundary directly.

Only single-component routes are representable today (see test_grading.py's
real Cambridge IGCSE Mathematics 0580 P1/Component 50 example). Most of that
qualification's real routes are NOT single-component: the overall grade
comes from a weighted combination of two components' raw marks, aggregated
into a combined total before any boundary applies - GradeBoundary has no
concept of that aggregation yet. Recorded here from the real June 2025
grade threshold table (cambridgeinternational.org/Images/741420-mathematics
-without-coursework-0580-june-2025-grade-threshold-table.pdf) so that future
multi-component work starts from real numbers instead of re-sourcing them:

    Option  Components  Max   A*   A    B    C   D   E   F   G
    AX      11, 31      160   -    -    -    86  72  59  46  33
    AY      12, 32      160   -    -    -    86  68  51  34  17
    AZ      13, 33      160   -    -    -    92  77  62  48  34
    BX      21, 41      200   156  131  106  81  68  55  -   -
    BY      22, 42      200   176  152  119  86  68  51  -   -
    BZ      23, 43      200   178  157  127  97  74  52  -   -
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
