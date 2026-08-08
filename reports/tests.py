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
from .services import _ges_grade, generate_class_reports, transition_report, update_report_details


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
        self.assertEqual(report.snapshot["class_teacher"], "report-teacher")
        self.assertEqual(report.snapshot["subjects"][0]["grade"], "3")
        self.assertEqual(report.snapshot["subjects"][0]["remark"], "High")

    def test_ges_grade_and_remark_boundaries(self):
        expected = {
            "95": ("1", "Highest"), "85": ("2", "Higher"),
            "75": ("3", "High"), "65": ("4", "High Average"),
            "57": ("5", "Average"), "52": ("6", "Low Average"),
            "45": ("7", "Low"), "35": ("8", "Lowest"),
            "20": ("9", "Fail"),
        }
        for score, result in expected.items():
            with self.subTest(score=score):
                self.assertEqual(_ges_grade(Decimal(score)), result)

    def test_report_prioritises_core_subjects_and_excludes_physical_education(self):
        for name in (
            "Career Technology", "Science", "English Language", "Physical Education", "Social Studies"
        ):
            subject = Subject.objects.create(school=self.school, name=name)
            SubjectOffering.objects.create(
                school=self.school, school_class=self.school_class, subject=subject, term=self.term
            )
        report = self._generate()
        self.assertEqual(
            [item["subject"] for item in report.snapshot["subjects"]],
            ["Social Studies", "English Language", "Mathematics", "Science", "Career Technology"],
        )

    def test_report_separates_weighted_class_and_exam_scores(self):
        self.category.weight = Decimal("50.00")
        self.category.name = "Class Score"
        self.category.save(update_fields=["weight", "name"])
        exam_category = AssessmentCategory.objects.create(
            scheme=self.scheme, name="Exam Score", code="end-of-term", weight=Decimal("50.00"), order=2
        )
        exam = Assessment.objects.create(
            school=self.school, offering=self.offering, category=exam_category,
            title="End-of-term examination", max_score=Decimal("100.00"), status=Assessment.Status.CLOSED,
        )
        GradeEntry.objects.create(
            school=self.school, assessment=exam, student=self.student, recorded_by=self.teacher,
            score=Decimal("82.00"), status=GradeEntry.Status.PUBLISHED,
            review_status=GradeEntry.ReviewStatus.APPROVED, reviewed_by=self.admin,
        )
        report = self._generate()
        result = report.snapshot["subjects"][0]
        self.assertEqual(result["class_score"], "36.00")
        self.assertEqual(result["exam_score"], "41.00")
        self.assertEqual(result["score"], "77.00")

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
        with self.assertRaisesMessage(ValidationError, "current workflow stage"):
            update_report_details(
                report=report, actor=self.teacher, conduct="Good", teacher_remark="Changed",
                promotion_outcome=TermReport.Promotion.PROMOTED,
            )

    def test_admin_edits_only_admin_fields_and_can_approve_draft_directly(self):
        report = self._generate(actor=self.admin)
        update_report_details(
            report=report, actor=self.admin, administrator_remark="Approved by headteacher",
            promotion_outcome=TermReport.Promotion.PROMOTED,
        )
        transition_report(report=report, actor=self.admin, action="approve")
        report.refresh_from_db()
        self.assertEqual(report.status, TermReport.Status.APPROVED)
        self.assertEqual(report.administrator_remark, "Approved by headteacher")

    def test_admin_cannot_submit_report_to_self(self):
        report = self._generate(actor=self.admin)
        with self.assertRaises(PermissionDenied):
            transition_report(report=report, actor=self.admin, action="submit")

    def test_reopen_error_does_not_invalidate_administrator_details_form(self):
        report = self._generate(actor=self.admin)
        transition_report(report=report, actor=self.admin, action="approve")
        transition_report(report=report, actor=self.admin, action="publish")
        self.client.force_login(self.admin.user)
        session = self.client.session
        session["active_school_id"] = self.school.pk
        session.save()
        response = self.client.post(
            reverse("term_report_detail", args=[report.pk]),
            {"form_type": "decision", "action": "reopen", "note": ""},
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["details_form"].is_bound)
        self.assertContains(response, "A reason is required.")
        self.assertNotContains(response, "This field is required.")

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

        merit = self.client.get(
            reverse("order_of_merit_pdf", args=[self.school_class.pk, self.term.pk]), secure=True
        )
        self.assertEqual(merit.status_code, 200)
        self.assertTrue(merit.content.startswith(b"%PDF"))
        self.assertIn("order-of-merit.pdf", merit["Content-Disposition"])

        promotion = self.client.get(
            reverse("promotion_list_pdf", args=[self.school_class.pk, self.term.pk]), secure=True
        )
        self.assertEqual(promotion.status_code, 200)
        self.assertTrue(promotion.content.startswith(b"%PDF"))
        self.assertIn("promotion-list.pdf", promotion["Content-Disposition"])

    def test_teacher_cannot_download_promotion_decisions(self):
        self.client.force_login(self.teacher.user)
        session = self.client.session
        session["active_school_id"] = self.school.pk
        session.save()
        response = self.client.get(
            reverse("promotion_list_pdf", args=[self.school_class.pk, self.term.pk]), secure=True
        )
        self.assertEqual(response.status_code, 403)

    def test_class_reports_support_bulk_teacher_and_admin_workflow(self):
        report = self._generate()
        url = reverse("class_term_reports", args=[self.school_class.pk, self.term.pk])
        self.client.force_login(self.teacher.user)
        session = self.client.session
        session["active_school_id"] = self.school.pk
        session.save()
        details = self.client.post(url, {
            "form_type": "bulk_details", "report_ids": [report.pk],
            "conduct": "Very good", "teacher_remark": "Keep progressing.",
        }, secure=True)
        self.assertEqual(details.status_code, 302)
        submit = self.client.post(url, {
            "form_type": "bulk_action", "report_ids": [report.pk], "action": "submit",
        }, secure=True)
        self.assertEqual(submit.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.status, TermReport.Status.PENDING)
        self.assertEqual(report.teacher_remark, "Keep progressing.")

        self.client.force_login(self.admin.user)
        session = self.client.session
        session["active_school_id"] = self.school.pk
        session.save()
        admin_details = self.client.post(url, {
            "form_type": "bulk_details", "report_ids": [report.pk],
            "administrator_remark": "Promoted to the next class.",
        }, secure=True)
        self.assertEqual(admin_details.status_code, 302)
        approve = self.client.post(url, {
            "form_type": "bulk_action", "report_ids": [report.pk], "action": "approve",
        }, secure=True)
        self.assertEqual(approve.status_code, 302)
        publish = self.client.post(url, {
            "form_type": "bulk_action", "report_ids": [report.pk], "action": "publish",
        }, secure=True)
        self.assertEqual(publish.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.status, TermReport.Status.PUBLISHED)
        self.assertEqual(report.administrator_remark, "Promoted to the next class.")

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
