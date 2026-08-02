from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, Term
from analytics.models import RiskSignal
from attendance.models import AttendanceRecord
from courses.models import Subject
from dashboard.models import LessonNote, LessonNoteEvent, LessonNoteNotification, LessonNoteVersion
from finance.models import Charge
from gradebook.models import GradeEntry
from guardians.models import GuardianLink
from reports.models import TermReport
from schools.models import School, SchoolMembership


class SeedDemoCommandTests(TestCase):
    @override_settings(NYANSA_DEMO_MODE=False)
    def test_command_refuses_to_run_outside_demo_mode(self):
        with self.assertRaisesMessage(CommandError, "demo"):
            call_command("seed_demo")

    @override_settings(NYANSA_DEMO_MODE=True)
    @patch.dict(
        "os.environ",
        {
            "DEMO_ADMIN_USERNAME": "demo-admin",
            "DEMO_ADMIN_PASSWORD": "safe-demo-password",
            "DEMO_ADMIN_EMAIL": "demo@example.com",
        },
    )
    def test_command_creates_idempotent_synthetic_school_data(self):
        call_command("seed_demo")
        call_command("seed_demo")

        user = get_user_model().objects.get(username="demo-admin")
        self.assertTrue(user.check_password("safe-demo-password"))
        self.assertTrue(user.is_staff)
        self.assertEqual(School.objects.count(), 1)
        self.assertEqual(
            SchoolMembership.objects.get(user=user).role,
            SchoolMembership.Role.SCHOOL_ADMIN,
        )
        self.assertEqual(AcademicYear.objects.count(), 1)
        self.assertEqual(Term.objects.count(), 1)
        self.assertEqual(SchoolClass.objects.count(), 1)
        self.assertEqual(Subject.objects.count(), 3)
        self.assertEqual(SchoolMembership.objects.count(), 5)
        self.assertEqual(ClassEnrollment.objects.count(), 2)
        self.assertEqual(SubjectOffering.objects.count(), 3)
        self.assertEqual(GradeEntry.objects.count(), 6)
        self.assertEqual(AttendanceRecord.objects.count(), 6)
        self.assertEqual(GuardianLink.objects.count(), 1)
        self.assertEqual(TermReport.objects.count(), 1)
        self.assertEqual(Charge.objects.count(), 2)
        self.assertEqual(RiskSignal.objects.count(), 1)
        self.assertEqual(LessonNote.objects.count(), 1)
        self.assertEqual(LessonNoteVersion.objects.count(), 1)
        self.assertEqual(LessonNoteEvent.objects.count(), 1)
        self.assertEqual(LessonNoteNotification.objects.count(), 1)
        self.assertEqual(LessonNote.objects.get().status, LessonNote.Status.PENDING_REVIEW)

    @override_settings(NYANSA_DEMO_MODE=True)
    @patch.dict(
        "os.environ",
        {
            "DEMO_ADMIN_USERNAME": "demo-admin",
            "DEMO_ADMIN_PASSWORD": "safe-demo-password",
            "DEMO_ADMIN_EMAIL": "demo@example.com",
        },
    )
    def test_command_preserves_an_administrator_selected_current_year(self):
        school = School.objects.create(name="Demo School", slug="nyansa-demo-school")
        selected_year = AcademicYear.objects.create(
            school=school,
            name="Administrator Year",
            start_date="2026-09-01",
            end_date="2027-07-31",
            is_current=True,
        )

        call_command("seed_demo")

        selected_year.refresh_from_db()
        self.assertTrue(selected_year.is_current)
        demo_year = AcademicYear.objects.exclude(pk=selected_year.pk).get(school=school)
        self.assertFalse(demo_year.is_current)
