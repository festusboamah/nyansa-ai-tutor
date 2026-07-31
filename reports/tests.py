from datetime import date
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, TeacherAssignment, Term
from accounts.models import User
from courses.models import Subject
from gradebook.models import Assessment, AssessmentCategory, GradeEntry, GradeScheme
from schools.models import School, SchoolMembership

from .models import ReportPolicy, ReportWorkflowEvent, TermReport
from .services import generate_class_reports, transition_report, update_report_details


class TermReportWorkflowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Nyansa Academy", slug="nyansa-academy", address="Accra, Ghana"
        )
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027", start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31), is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", order=1,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
        )
        self.teacher = self._membership("report-teacher", SchoolMembership.Role.TEACHER, User.Role.TEACHER)
        self.admin = self._membership("report-admin", SchoolMembership.Role.SCHOOL_ADMIN, User.Role.TEACHER)
        self.student = self._membership("report-student", SchoolMembership.Role.STUDENT, User.Role.STUDENT)
        self.school_class = SchoolClass.objects.create(
            school=self.school, academic_year=self.year, name="Basic 6", class_teacher=self.teacher
        )
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.student)
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.offering = SubjectOffering.objects.create(
            school=self.school, school_class=self.school_class, subject=self.subject, term=self.term
        )
        TeacherAssignment.objects.create(offering=self.offering, teacher=self.teacher, is_lead=True)
        self.scheme = GradeScheme.objects.create(
            school=self.school, academic_year=self.year, name="Standard", status=GradeScheme.Status.ACTIVE
        )
        self.category = AssessmentCategory.objects.create(
            scheme=self.scheme, name="Term work", code="term-work", weight=Decimal("100.00"), order=1
        )
        self.assessment = Assessment.objects.create(
            school=self.school, offering=self.offering, category=self.category,
            title="Final assessment", max_score=Decimal("100.00"), status=Assessment.Status.CLOSED,
        )
        self.grade = GradeEntry.objects.create(
            school=self.school, assessment=self.assessment, student=self.student,
            recorded_by=self.teacher, score=Decimal("72.00"), status=GradeEntry.Status.PUBLISHED,
            review_status=GradeEntry.ReviewStatus.APPROVED, reviewed_by=self.admin,
        )

    def _membership(self, username, membership_role, user_role):
        user = User.objects.create_user(username=username, password="test-password", role=user_role)
        return SchoolMembership.objects.create(school=self.school, user=user, role=membership_role)

    def _generate(self, actor=None):
        return generate_class_reports(
            school_class=self.school_class, term=self.term, actor=actor or self.teacher
        )[0]

    def test_generation_snapshots_approved_results_attendance_and_branding(self):
        report = self._generate()
        self.assertEqual(report.average_score, Decimal("72.00"))
        self.assertEqual(report.snapshot["subjects"][0]["score"], "72.00")
        self.assertEqual(report.snapshot["attendance"]["days_open"], 5)
        self.assertEqual(report.snapshot["school"]["name"], "Nyansa Academy")
        self.assertEqual(report.promotion_outcome, TermReport.Promotion.PROMOTED)

    def test_unapproved_grade_is_not_an_official_source(self):
        self.grade.review_status = GradeEntry.ReviewStatus.PENDING
        self.grade.save(update_fields=["review_status"])
        report = self._generate()
        self.assertIsNone(report.average_score)
        self.assertIsNone(report.snapshot["subjects"][0]["score"])

    def test_position_policy_handles_ties(self):
        second = self._membership("second-student", SchoolMembership.Role.STUDENT, User.Role.STUDENT)
        ClassEnrollment.objects.create(school_class=self.school_class, student=second)
        GradeEntry.objects.create(
            school=self.school, assessment=self.assessment, student=second,
            recorded_by=self.teacher, score=Decimal("72"), status=GradeEntry.Status.PUBLISHED,
            review_status=GradeEntry.ReviewStatus.APPROVED, reviewed_by=self.admin,
        )
        ReportPolicy.objects.create(school=self.school, academic_year=self.year, show_position=True)
        reports = generate_class_reports(school_class=self.school_class, term=self.term, actor=self.teacher)
        self.assertEqual([report.position for report in reports], [1, 1])

    def test_snapshot_compares_the_latest_published_prior_term(self):
        prior = Term.objects.create(
            academic_year=self.year, name="Opening Term", order=0,
            start_date=date(2026, 9, 1), end_date=date(2026, 9, 5),
        )
        TermReport.objects.create(
            school=self.school, school_class=self.school_class, term=prior, student=self.student,
            status=TermReport.Status.PUBLISHED, prepared_by=self.teacher,
            snapshot={"average": "65.00"}, total_score=Decimal("65"), average_score=Decimal("65"),
        )
        report = self._generate()
        self.assertEqual(report.snapshot["prior_term"]["average"], "65.00")
        self.assertEqual(report.snapshot["prior_term"]["change"], "7.00")

    def test_published_snapshot_stays_stable_until_explicit_reopen(self):
        report = self._generate()
        transition_report(report=report, actor=self.teacher, action="submit")
        transition_report(report=report, actor=self.admin, action="approve")
        transition_report(report=report, actor=self.admin, action="publish")
        self.grade.score = Decimal("95")
        self.grade.save(update_fields=["score"])
        generate_class_reports(school_class=self.school_class, term=self.term, actor=self.teacher)
        report.refresh_from_db()
        self.assertEqual(report.status, TermReport.Status.PUBLISHED)
        self.assertEqual(report.snapshot["average"], "72.00")
        transition_report(report=report, actor=self.admin, action="reopen", note="Approved correction")
        report.refresh_from_db()
        self.assertEqual(report.version, 2)
        self.assertEqual(report.status, TermReport.Status.DRAFT)

    def test_workflow_enforces_admin_review_and_reason(self):
        report = self._generate()
        transition_report(report=report, actor=self.teacher, action="submit")
        with self.assertRaises(PermissionDenied):
            transition_report(report=report, actor=self.teacher, action="approve")
        with self.assertRaisesMessage(ValidationError, "reason"):
            transition_report(report=report, actor=self.admin, action="return")
        transition_report(report=report, actor=self.admin, action="return", note="Check remark")
        report.refresh_from_db()
        self.assertEqual(report.status, TermReport.Status.RETURNED)

    def test_published_report_cannot_be_silently_edited(self):
        report = self._generate()
        transition_report(report=report, actor=self.teacher, action="submit")
        transition_report(report=report, actor=self.admin, action="approve")
        transition_report(report=report, actor=self.admin, action="publish")
        with self.assertRaisesMessage(ValidationError, "draft or returned"):
            update_report_details(
                report=report, actor=self.teacher, conduct="Good", teacher_remark="Changed",
                promotion_outcome=TermReport.Promotion.PROMOTED,
            )

    def test_workflow_history_is_immutable(self):
        report = self._generate()
        event = report.workflow_events.first()
        event.note = "Changed"
        with self.assertRaisesMessage(ValidationError, "immutable"):
            event.save()
        with self.assertRaisesMessage(ValidationError, "immutable"):
            event.delete()

    def test_cross_school_teacher_cannot_generate(self):
        other = School.objects.create(name="Other", slug="other")
        other_user = User.objects.create_user(username="other-report-teacher", password="test-password")
        outsider = SchoolMembership.objects.create(
            school=other, user=other_user, role=SchoolMembership.Role.TEACHER
        )
        with self.assertRaises(PermissionDenied):
            self._generate(actor=outsider)

    def test_report_pdf_and_bulk_zip_are_downloadable(self):
        report = self._generate(actor=self.admin)
        transition_report(report=report, actor=self.admin, action="submit")
        transition_report(report=report, actor=self.admin, action="approve")
        transition_report(report=report, actor=self.admin, action="publish")
        self.client.force_login(self.admin.user)
        session = self.client.session
        session["active_school_id"] = self.school.pk
        session.save()
        pdf = self.client.get(reverse("term_report_pdf", args=[report.pk]), secure=True)
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        archive_response = self.client.get(
            reverse("class_term_reports_zip", args=[self.school_class.pk, self.term.pk]), secure=True
        )
        self.assertEqual(archive_response.status_code, 200)
        with ZipFile(BytesIO(archive_response.content)) as archive:
            self.assertEqual(len(archive.namelist()), 1)

    def test_other_school_report_is_not_visible(self):
        report = self._generate()
        other = School.objects.create(name="Other School", slug="other-school")
        user = User.objects.create_user(username="other-admin", password="test-password", role=User.Role.TEACHER)
        SchoolMembership.objects.create(school=other, user=user, role=SchoolMembership.Role.SCHOOL_ADMIN)
        self.client.force_login(user)
        session = self.client.session
        session["active_school_id"] = other.pk
        session.save()
        response = self.client.get(reverse("term_report_detail", args=[report.pk]), secure=True)
        self.assertEqual(response.status_code, 404)
