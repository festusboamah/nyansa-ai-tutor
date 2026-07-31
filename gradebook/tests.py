from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, Term
from accounts.models import User
from courses.models import Subject
from schools.models import School, SchoolMembership

from .models import Assessment, AssessmentCategory, GradeEntry, GradeScheme
from .services import activate_grade_scheme, calculate_weighted_result


class GradebookTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Nyansa School", slug="nyansa-school")
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31),
            is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name="Term 1",
            order=1,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 15),
        )
        self.school_class = SchoolClass.objects.create(
            school=self.school, academic_year=self.year, name="JHS 1"
        )
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.offering = SubjectOffering.objects.create(
            school=self.school,
            school_class=self.school_class,
            subject=self.subject,
            term=self.term,
        )
        self.student = self._membership("student", SchoolMembership.Role.STUDENT)
        self.teacher = self._membership("teacher", SchoolMembership.Role.TEACHER)
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.student)
        self.scheme = GradeScheme.objects.create(
            school=self.school, academic_year=self.year, name="Standard"
        )
        self.coursework = AssessmentCategory.objects.create(
            scheme=self.scheme, name="Coursework", code="coursework", weight=Decimal("40.00"), order=1
        )
        self.exam = AssessmentCategory.objects.create(
            scheme=self.scheme, name="Exam", code="exam", weight=Decimal("60.00"), order=2
        )

    def _membership(self, username, role, school=None):
        user = User.objects.create_user(username=username, password="test-password")
        return SchoolMembership.objects.create(school=school or self.school, user=user, role=role)

    def _assessment(self, category, title, max_score="100.00"):
        return Assessment.objects.create(
            school=self.school,
            offering=self.offering,
            category=category,
            title=title,
            max_score=Decimal(max_score),
            status=Assessment.Status.PUBLISHED,
        )

    def test_scheme_activation_requires_weights_totaling_100_percent(self):
        self.exam.weight = Decimal("50.00")
        self.exam.save(update_fields=["weight"])
        with self.assertRaisesMessage(ValidationError, "current total is 90"):
            activate_grade_scheme(self.scheme)
        self.scheme.refresh_from_db()
        self.assertEqual(self.scheme.status, GradeScheme.Status.DRAFT)

    def test_activating_scheme_archives_previous_scheme_for_year(self):
        old = GradeScheme.objects.create(
            school=self.school,
            academic_year=self.year,
            name="Old scheme",
            status=GradeScheme.Status.ACTIVE,
        )
        activate_grade_scheme(self.scheme)
        old.refresh_from_db()
        self.scheme.refresh_from_db()
        self.assertEqual(old.status, GradeScheme.Status.ARCHIVED)
        self.assertEqual(self.scheme.status, GradeScheme.Status.ACTIVE)

    def test_assessment_rejects_category_from_another_school(self):
        other = School.objects.create(name="Other School", slug="other-school")
        other_year = AcademicYear.objects.create(
            school=other,
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31),
        )
        other_scheme = GradeScheme.objects.create(school=other, academic_year=other_year, name="Other")
        other_category = AssessmentCategory.objects.create(
            scheme=other_scheme, name="Exam", code="exam", weight=Decimal("100"), order=1
        )
        assessment = Assessment(
            school=self.school,
            offering=self.offering,
            category=other_category,
            title="Wrong tenant",
            max_score=Decimal("100"),
        )
        with self.assertRaises(ValidationError):
            assessment.full_clean()

    def test_grade_rejects_score_above_maximum(self):
        assessment = self._assessment(self.coursework, "Quiz", "20")
        entry = GradeEntry(
            school=self.school,
            assessment=assessment,
            student=self.student,
            recorded_by=self.teacher,
            score=Decimal("21"),
        )
        with self.assertRaisesMessage(ValidationError, "Score cannot exceed"):
            entry.full_clean()

    def test_grade_rejects_student_not_enrolled_in_assessment_class(self):
        outsider = self._membership("outsider", SchoolMembership.Role.STUDENT)
        assessment = self._assessment(self.coursework, "Class test")
        entry = GradeEntry(
            school=self.school,
            assessment=assessment,
            student=outsider,
            recorded_by=self.teacher,
            score=Decimal("70"),
        )
        with self.assertRaisesMessage(ValidationError, "actively enrolled"):
            entry.full_clean()

    def test_grade_rejects_cross_school_recorder(self):
        other = School.objects.create(name="Other School", slug="other-school")
        recorder = self._membership("other-teacher", SchoolMembership.Role.TEACHER, school=other)
        assessment = self._assessment(self.coursework, "Project")
        entry = GradeEntry(
            school=self.school,
            assessment=assessment,
            student=self.student,
            recorded_by=recorder,
            score=Decimal("70"),
        )
        with self.assertRaisesMessage(ValidationError, "same school"):
            entry.full_clean()

    def test_weighted_result_uses_published_entries_and_reweights_available_categories(self):
        coursework = self._assessment(self.coursework, "Project", "50")
        exam = self._assessment(self.exam, "End-of-term exam")
        GradeEntry.objects.create(
            school=self.school,
            assessment=coursework,
            student=self.student,
            recorded_by=self.teacher,
            score=Decimal("40"),
            status=GradeEntry.Status.PUBLISHED,
        )
        GradeEntry.objects.create(
            school=self.school,
            assessment=exam,
            student=self.student,
            recorded_by=self.teacher,
            score=Decimal("50"),
            status=GradeEntry.Status.DRAFT,
        )
        result = calculate_weighted_result(
            student=self.student, offering=self.offering, scheme=self.scheme
        )
        self.assertEqual(result["final_score"], Decimal("80.00"))
        self.assertEqual(result["used_weight"], Decimal("40.00"))

    def test_weighted_result_combines_category_averages(self):
        coursework = self._assessment(self.coursework, "Project", "50")
        exam = self._assessment(self.exam, "Exam")
        for assessment, score in ((coursework, "40"), (exam, "50")):
            GradeEntry.objects.create(
                school=self.school,
                assessment=assessment,
                student=self.student,
                recorded_by=self.teacher,
                score=Decimal(score),
                status=GradeEntry.Status.PUBLISHED,
            )
        result = calculate_weighted_result(
            student=self.student, offering=self.offering, scheme=self.scheme
        )
        self.assertEqual(result["final_score"], Decimal("62.00"))
        self.assertEqual(result["used_weight"], Decimal("100.00"))
