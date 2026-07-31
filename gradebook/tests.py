from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, TeacherAssignment, Term
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


class TeacherGradebookWorkflowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Workflow School", slug="workflow-school")
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
            school=self.school, academic_year=self.year, name="Basic 6"
        )
        self.subject = Subject.objects.create(school=self.school, name="English")
        self.offering = SubjectOffering.objects.create(
            school=self.school,
            school_class=self.school_class,
            subject=self.subject,
            term=self.term,
        )
        self.teacher_user = User.objects.create_user(
            username="grade-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.teacher = SchoolMembership.objects.create(
            school=self.school, user=self.teacher_user, role=SchoolMembership.Role.TEACHER
        )
        TeacherAssignment.objects.create(offering=self.offering, teacher=self.teacher, is_lead=True)
        self.other_teacher_user = User.objects.create_user(
            username="other-grade-teacher", password="test-password", role=User.Role.TEACHER
        )
        SchoolMembership.objects.create(
            school=self.school, user=self.other_teacher_user, role=SchoolMembership.Role.TEACHER
        )
        self.student_memberships = []
        for number in (1, 2):
            user = User.objects.create_user(username=f"roster-student-{number}", password="test-password")
            membership = SchoolMembership.objects.create(
                school=self.school, user=user, role=SchoolMembership.Role.STUDENT
            )
            ClassEnrollment.objects.create(school_class=self.school_class, student=membership)
            self.student_memberships.append(membership)
        self.scheme = GradeScheme.objects.create(
            school=self.school,
            academic_year=self.year,
            name="Active scheme",
            status=GradeScheme.Status.ACTIVE,
        )
        self.category = AssessmentCategory.objects.create(
            scheme=self.scheme, name="Classwork", code="classwork", weight=Decimal("100"), order=1
        )
        self.assessment = Assessment.objects.create(
            school=self.school,
            offering=self.offering,
            category=self.category,
            title="Writing exercise",
            max_score=Decimal("20"),
            status=Assessment.Status.PUBLISHED,
        )

    def test_teacher_only_sees_assigned_offerings(self):
        other_subject = Subject.objects.create(school=self.school, name="Science")
        SubjectOffering.objects.create(
            school=self.school,
            school_class=self.school_class,
            subject=other_subject,
            term=self.term,
        )
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse("gradebook_offerings"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "English")
        self.assertNotContains(response, "Science")

    def test_unassigned_teacher_cannot_open_assessment_roster(self):
        self.client.force_login(self.other_teacher_user)
        response = self.client.get(reverse("gradebook_roster", args=[self.assessment.pk]), secure=True)
        self.assertEqual(response.status_code, 404)

    def test_student_membership_cannot_open_gradebook(self):
        self.client.force_login(self.student_memberships[0].user)
        response = self.client.get(reverse("gradebook_offerings"), secure=True)
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_teacher_can_create_assessment_from_active_scheme(self):
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            reverse("gradebook_create_assessment", args=[self.offering.pk]),
            {
                "category": self.category.pk,
                "title": "Vocabulary quiz",
                "max_score": "15.00",
                "due_at": "",
                "status": Assessment.Status.DRAFT,
            },
            secure=True,
        )
        created = Assessment.objects.get(title="Vocabulary quiz")
        self.assertRedirects(response, reverse("gradebook_roster", args=[created.pk]), fetch_redirect_response=False)
        self.assertEqual(created.school, self.school)
        self.assertEqual(created.offering, self.offering)

    def test_invalid_roster_submission_is_atomic(self):
        first, second = self.student_memberships
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            reverse("gradebook_roster", args=[self.assessment.pk]),
            {f"score_{first.pk}": "18", f"score_{second.pk}": "25", "action": "publish"},
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Score cannot exceed")
        self.assertFalse(GradeEntry.objects.filter(assessment=self.assessment).exists())

    def test_teacher_can_save_draft_and_publish_roster_scores(self):
        first, second = self.student_memberships
        self.client.force_login(self.teacher_user)
        url = reverse("gradebook_roster", args=[self.assessment.pk])
        self.client.post(
            url,
            {f"score_{first.pk}": "16", f"score_{second.pk}": "14", "action": "draft"},
            secure=True,
        )
        self.assertEqual(
            set(GradeEntry.objects.filter(assessment=self.assessment).values_list("status", flat=True)),
            {GradeEntry.Status.DRAFT},
        )
        self.client.post(
            url,
            {f"score_{first.pk}": "17", f"score_{second.pk}": "15", "action": "publish"},
            secure=True,
        )
        entries = GradeEntry.objects.filter(assessment=self.assessment)
        self.assertEqual(set(entries.values_list("status", flat=True)), {GradeEntry.Status.PUBLISHED})
        self.assertEqual(set(entries.values_list("source", flat=True)), {GradeEntry.Source.MANUAL})
        self.assertEqual(set(entries.values_list("recorded_by", flat=True)), {self.teacher.pk})

    def test_closed_assessment_cannot_be_changed(self):
        self.assessment.status = Assessment.Status.CLOSED
        self.assessment.save(update_fields=["status"])
        self.client.force_login(self.teacher_user)
        self.client.post(
            reverse("gradebook_roster", args=[self.assessment.pk]),
            {f"score_{self.student_memberships[0].pk}": "10", "action": "publish"},
            secure=True,
        )
        self.assertFalse(GradeEntry.objects.filter(assessment=self.assessment).exists())
