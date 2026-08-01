from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, TeacherAssignment, Term
from accounts.models import User
from attendance.models import AttendanceRecord, AttendanceSession
from courses.models import Subject
from gradebook.models import Assessment, AssessmentCategory, GradeEntry, GradeScheme
from reports.models import TermReport
from schools.models import School, SchoolMembership

from .models import EarlyWarningPolicy, NarrativeSnapshot, RiskSignal
from .services import (
    approve_narrative, class_metrics, complete_intervention, create_intervention, create_narrative,
    generate_risk_signals, offering_metrics, school_metrics,
)


class AnalyticsWorkflowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Insight School", slug="insight-school")
        self.admin = self._member("insight-admin", SchoolMembership.Role.SCHOOL_ADMIN)
        self.teacher = self._member("insight-teacher", SchoolMembership.Role.TEACHER)
        self.unassigned = self._member("unassigned-insight-teacher", SchoolMembership.Role.TEACHER)
        self.student = self._member("insight-student", SchoolMembership.Role.STUDENT)
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027", start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31), is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", order=1,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
        )
        self.school_class = SchoolClass.objects.create(
            school=self.school, academic_year=self.year, name="Basic 6", class_teacher=self.teacher
        )
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.student)
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.offering = SubjectOffering.objects.create(
            school=self.school, school_class=self.school_class, subject=self.subject, term=self.term
        )
        TeacherAssignment.objects.create(offering=self.offering, teacher=self.teacher)
        self.scheme = GradeScheme.objects.create(
            school=self.school, academic_year=self.year, name="Standard", status=GradeScheme.Status.ACTIVE
        )
        self.category = AssessmentCategory.objects.create(
            scheme=self.scheme, name="Coursework", code="coursework", weight=Decimal("100"), order=1
        )
        self.assessment_one = self._assessment("Test one")
        self.assessment_two = self._assessment("Test two")
        self.assessment_missing = self._assessment("Project")
        self._grade(self.assessment_one, "40")
        self._grade(self.assessment_two, "60")
        TermReport.objects.create(
            school=self.school, school_class=self.school_class, term=self.term, student=self.student,
            status=TermReport.Status.PUBLISHED, prepared_by=self.teacher,
            total_score=Decimal("45"), average_score=Decimal("45"), snapshot={"average": "45.00"},
        )
        for index, day in enumerate(range(7, 12)):
            session = AttendanceSession.objects.create(
                school=self.school, school_class=self.school_class, term=self.term,
                attendance_date=date(2026, 9, day), status=AttendanceSession.Status.SUBMITTED,
                submitted_by=self.teacher,
            )
            AttendanceRecord.objects.create(
                session=session, student=self.student,
                status=AttendanceRecord.Status.PRESENT if index < 3 else AttendanceRecord.Status.ABSENT,
                marked_by=self.teacher,
            )

    def _member(self, username, role):
        user = User.objects.create_user(username=username, password="test-password", role=User.Role.TEACHER if role != "STUDENT" else User.Role.STUDENT)
        return SchoolMembership.objects.create(school=self.school, user=user, role=role)

    def _assessment(self, title):
        return Assessment.objects.create(
            school=self.school, offering=self.offering, category=self.category,
            title=title, max_score=Decimal("100"), status=Assessment.Status.CLOSED,
        )

    def _grade(self, assessment, score):
        return GradeEntry.objects.create(
            school=self.school, assessment=assessment, student=self.student,
            recorded_by=self.teacher, score=Decimal(score), status=GradeEntry.Status.PUBLISHED,
            review_status=GradeEntry.ReviewStatus.APPROVED, reviewed_by=self.admin,
        )

    def _login(self, membership):
        self.client.force_login(membership.user)
        session = self.client.session
        session["active_school_id"] = self.school.pk
        session.save()

    def test_offering_trend_uses_only_published_approved_entries(self):
        metrics = offering_metrics(self.offering)
        self.assertEqual(metrics["assessments"][0]["average"], Decimal("40.00"))
        self.assertEqual(metrics["latest_average"], Decimal("60.00"))
        self.assertEqual(metrics["change_from_previous"], Decimal("20.00"))
        self.assertIn("approved", metrics["source"])

    def test_class_and_school_metrics_agree_with_authoritative_records(self):
        metrics = class_metrics(self.school_class, self.term)
        self.assertEqual(metrics["academic_average"], Decimal("45.00"))
        self.assertEqual(metrics["attendance_percentage"], Decimal("60.00"))
        self.assertEqual(metrics["days_open"], 5)
        school = school_metrics(self.school, self.term)
        self.assertEqual(school["academic_average"], Decimal("45.00"))
        self.assertEqual(school["attendance_percentage"], Decimal("60.00"))
        self.assertEqual(school["period"], "2026/2027 · Term 1")

    def test_warning_rules_create_explainable_signals(self):
        EarlyWarningPolicy.objects.create(
            school=self.school, name="Academic support", metric=EarlyWarningPolicy.Metric.LOW_AVERAGE,
            threshold=Decimal("50"), created_by=self.admin,
        )
        EarlyWarningPolicy.objects.create(
            school=self.school, name="Attendance support", metric=EarlyWarningPolicy.Metric.LOW_ATTENDANCE,
            threshold=Decimal("70"), created_by=self.admin,
        )
        EarlyWarningPolicy.objects.create(
            school=self.school, name="Missing evidence", metric=EarlyWarningPolicy.Metric.MISSING_GRADES,
            threshold=Decimal("1"), created_by=self.admin,
        )
        signals = generate_risk_signals(
            school_class=self.school_class, term=self.term, actor=self.teacher
        )
        self.assertEqual(len(signals), 3)
        for signal in signals:
            self.assertEqual(signal.evidence["period"], "2026/2027 · Term 1")
            self.assertTrue(signal.evidence["source"])

    def test_signal_resolves_when_source_metric_recovers_and_can_reopen(self):
        policy = EarlyWarningPolicy.objects.create(
            school=self.school, name="Academic threshold", metric=EarlyWarningPolicy.Metric.LOW_AVERAGE,
            threshold=Decimal("50"), created_by=self.admin,
        )
        signal = generate_risk_signals(school_class=self.school_class, term=self.term, actor=self.teacher)[0]
        report = self.student.term_reports.get(term=self.term)
        report.average_score = Decimal("75")
        report.save(update_fields=["average_score"])
        generate_risk_signals(school_class=self.school_class, term=self.term, actor=self.teacher)
        signal.refresh_from_db()
        self.assertEqual(signal.status, RiskSignal.Status.RESOLVED)
        report.average_score = Decimal("40")
        report.save(update_fields=["average_score"])
        generate_risk_signals(school_class=self.school_class, term=self.term, actor=self.teacher)
        signal.refresh_from_db()
        self.assertEqual(signal.status, RiskSignal.Status.OPEN)

    def test_intervention_requires_staff_with_class_access(self):
        policy = EarlyWarningPolicy.objects.create(
            school=self.school, name="Support", metric=EarlyWarningPolicy.Metric.LOW_AVERAGE,
            threshold=Decimal("50"), created_by=self.admin,
        )
        signal = generate_risk_signals(school_class=self.school_class, term=self.term, actor=self.teacher)[0]
        intervention = create_intervention(
            signal=signal, actor=self.teacher, owner=self.teacher,
            plan="Meet learner weekly and review practice evidence.",
        )
        self.assertEqual(intervention.signal.status, RiskSignal.Status.ACKNOWLEDGED)
        complete_intervention(
            intervention=intervention, actor=self.teacher,
            outcome="Attendance and weekly work improved after four reviews.",
        )
        intervention.refresh_from_db()
        signal.refresh_from_db()
        self.assertEqual(intervention.status, intervention.Status.COMPLETED)
        self.assertEqual(signal.status, RiskSignal.Status.RESOLVED)
        with self.assertRaises(PermissionDenied):
            create_intervention(
                signal=signal, actor=self.unassigned, owner=self.teacher,
                plan="Unauthorized plan should not be accepted.",
            )

    def test_grounded_narrative_freezes_metrics_and_requires_admin_approval(self):
        metrics = school_metrics(self.school, self.term)
        narrative = create_narrative(
            school=self.school, term=self.term, actor=self.admin,
            scope=NarrativeSnapshot.Scope.SCHOOL, metrics=metrics,
        )
        self.assertEqual(narrative.metrics_snapshot["academic_average"], "45.00")
        self.assertIn("Period: 2026/2027 · Term 1", narrative.narrative)
        with self.assertRaises(PermissionDenied):
            approve_narrative(narrative=narrative, actor=self.teacher)
        approve_narrative(narrative=narrative, actor=self.admin)
        narrative.refresh_from_db()
        self.assertEqual(narrative.status, NarrativeSnapshot.Status.APPROVED)

    def test_unassigned_teacher_cannot_drill_into_class_or_offering(self):
        self._login(self.unassigned)
        class_response = self.client.get(
            reverse("analytics_class", args=[self.school_class.pk, self.term.pk]), secure=True
        )
        offering_response = self.client.get(
            reverse("analytics_offering", args=[self.offering.pk]), secure=True
        )
        self.assertEqual(class_response.status_code, 403)
        self.assertEqual(offering_response.status_code, 403)

    def test_cross_school_signal_is_not_visible(self):
        policy = EarlyWarningPolicy.objects.create(
            school=self.school, name="Private support", metric=EarlyWarningPolicy.Metric.LOW_AVERAGE,
            threshold=Decimal("50"), created_by=self.admin,
        )
        signal = generate_risk_signals(school_class=self.school_class, term=self.term, actor=self.teacher)[0]
        other = School.objects.create(name="Other Insight", slug="other-insight")
        user = User.objects.create_user(username="other-insight-admin", password="test-password")
        member = SchoolMembership.objects.create(school=other, user=user, role=SchoolMembership.Role.SCHOOL_ADMIN)
        self.client.force_login(user)
        session = self.client.session
        session["active_school_id"] = other.pk
        session.save()
        response = self.client.get(reverse("analytics_signal", args=[signal.pk]), secure=True)
        self.assertEqual(response.status_code, 404)
