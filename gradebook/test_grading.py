from datetime import date
from decimal import Decimal

from django.test import TestCase

from academics.models import AcademicYear
from courses.models import Subject
from schools.models import School

from .grading import resolve_grade
from .models import GradeBoundary, GradeScheme


class ResolveGradeTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Boundary School", slug="boundary-school")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027",
            start_date=date(2026, 9, 1), end_date=date(2027, 7, 31), is_current=True,
        )
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.scheme = GradeScheme.objects.create(
            school=self.school, academic_year=self.year, name="Cambridge",
            boundary_type=GradeScheme.BoundaryType.DYNAMIC_MARK,
        )

    def _boundary(self, grade, minimum_mark, reference_max_mark="70", subject=None, grade_point=None):
        return GradeBoundary.objects.create(
            scheme=self.scheme, subject=subject, grade=grade,
            minimum_mark=Decimal(minimum_mark), reference_max_mark=Decimal(reference_max_mark),
            grade_point=Decimal(grade_point) if grade_point is not None else None,
        )

    def test_returns_none_when_no_boundaries_are_configured(self):
        self.assertIsNone(resolve_grade(Decimal("70"), scheme=self.scheme, subject=self.subject))

    def test_resolves_a_mark_entered_exactly_as_published(self):
        # Real Cambridge-style boundaries: "49 out of 70" for a Mathematics paper.
        self._boundary("A*", "56", subject=self.subject, grade_point="4.30")
        self._boundary("A", "49", subject=self.subject, grade_point="4.00")
        self._boundary("B", "42", subject=self.subject, grade_point="3.00")
        self._boundary("C", "35", subject=self.subject, grade_point="2.00")

        # 49/70 = 70.00% - should land exactly on the A boundary.
        grade, grade_point = resolve_grade(Decimal("70.00"), scheme=self.scheme, subject=self.subject)
        self.assertEqual(grade, "A")
        self.assertEqual(grade_point, Decimal("4.00"))

    def test_a_score_just_below_a_boundary_falls_to_the_next_grade_down(self):
        self._boundary("A", "49", subject=self.subject)
        self._boundary("B", "42", subject=self.subject)

        # 48/70 = 68.57%, just under the A threshold (70.00%).
        grade, _ = resolve_grade(Decimal("68.57"), scheme=self.scheme, subject=self.subject)
        self.assertEqual(grade, "B")

    def test_year_over_year_boundary_changes_are_just_a_different_scheme(self):
        self._boundary("A", "49", subject=self.subject)
        next_year = AcademicYear.objects.create(
            school=self.school, name="2027/2028",
            start_date=date(2027, 9, 1), end_date=date(2028, 7, 31),
        )
        next_scheme = GradeScheme.objects.create(
            school=self.school, academic_year=next_year, name="Cambridge",
            boundary_type=GradeScheme.BoundaryType.DYNAMIC_MARK,
        )
        GradeBoundary.objects.create(
            scheme=next_scheme, subject=self.subject, grade="A", minimum_mark=Decimal("47"), reference_max_mark=Decimal("70"),
        )

        # Same 68.57% (48/70): this year's boundary (A >= 49) doesn't clear it,
        # so no grade resolves at all (only "A" is configured); next year's
        # slightly lower boundary (A >= 47) does.
        this_year_grade = resolve_grade(Decimal("68.57"), scheme=self.scheme, subject=self.subject)
        next_year_grade, _ = resolve_grade(Decimal("68.57"), scheme=next_scheme, subject=self.subject)
        self.assertIsNone(this_year_grade)
        self.assertEqual(next_year_grade, "A")

    def test_subject_specific_boundaries_take_precedence_over_scheme_wide(self):
        other_subject = Subject.objects.create(school=self.school, name="English Language")
        GradeBoundary.objects.create(
            scheme=self.scheme, subject=None, grade="A", minimum_mark=Decimal("80"), reference_max_mark=Decimal("100"),
        )
        self._boundary("A", "49", subject=self.subject)  # 49/70 = 70.00%

        # 72% clears the subject-specific 70% threshold (49/70) but not the
        # scheme-wide 80% one - confirms the subject-specific row wins.
        grade, _ = resolve_grade(Decimal("72"), scheme=self.scheme, subject=self.subject)
        self.assertEqual(grade, "A")

        # A different subject with no boundaries of its own falls back to the
        # scheme-wide row.
        other_grade = resolve_grade(Decimal("85"), scheme=self.scheme, subject=other_subject)
        self.assertEqual(other_grade, ("A", None))

    def test_configurable_percentage_scheme_wide_bands(self):
        percentage_scheme = GradeScheme.objects.create(
            school=self.school, academic_year=self.year, name="School Bands",
            boundary_type=GradeScheme.BoundaryType.CONFIGURABLE_PERCENTAGE,
        )
        GradeBoundary.objects.create(scheme=percentage_scheme, subject=None, grade="A", minimum_mark=Decimal("80"))
        GradeBoundary.objects.create(scheme=percentage_scheme, subject=None, grade="B", minimum_mark=Decimal("70"))
        GradeBoundary.objects.create(scheme=percentage_scheme, subject=None, grade="F", minimum_mark=Decimal("0"))

        grade, _ = resolve_grade(Decimal("75"), scheme=percentage_scheme, subject=self.subject)
        self.assertEqual(grade, "B")

    def test_resolves_the_real_2025_igcse_mathematics_component_50_thresholds(self):
        # Real data, not illustrative round numbers: Cambridge IGCSE
        # Mathematics (0580), June 2025, Option P1 (standalone Component 50) -
        # the one route in this qualification's real table that's a single
        # component, not a weighted combination of two (which resolve_grade
        # doesn't support yet - see this module's docstring for the full
        # table and that caveat).
        # Source: cambridgeinternational.org/Images/741420-mathematics-without-coursework-0580-june-2025-grade-threshold-table.pdf
        for grade, minimum in [
            ("A*", "77"), ("A", "67"), ("B", "57"), ("C", "47"),
            ("D", "38"), ("E", "30"), ("F", "21"), ("G", "12"),
        ]:
            self._boundary(grade, minimum, reference_max_mark="90", subject=self.subject)

        # A student scoring exactly the published B threshold (57/90 = 63.33%).
        grade, _ = resolve_grade(Decimal("57") / Decimal("90") * 100, scheme=self.scheme, subject=self.subject)
        self.assertEqual(grade, "B")
