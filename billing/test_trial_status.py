from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from communications.models import Notification
from schools.models import School, SchoolMembership

from .models import LicensePlan, SchoolLicense
from .services import TRIAL_LENGTH_DAYS, check_trial_statuses


class TrialLengthTests(TestCase):
    def test_starting_a_trial_grants_fourteen_days(self):
        self.assertEqual(TRIAL_LENGTH_DAYS, 14)

        school = School.objects.create(name="Trial Length School", slug="trial-length-school")
        user = User.objects.create_user(username="new-admin", password="test-password")
        SchoolMembership.objects.create(school=school, user=user, role=SchoolMembership.Role.SCHOOL_ADMIN)
        self.client.force_login(user)
        plan = LicensePlan.objects.get(code=LicensePlan.Code.STANDARD)

        self.client.post(reverse("billing_plans"), {"plan_id": plan.id}, secure=True)

        license = SchoolLicense.objects.get(school=school)
        self.assertEqual((license.current_period_end - license.current_period_start).days, 14)


class CheckTrialStatusesTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Trial Status School", slug="trial-status-school")
        admin_user = User.objects.create_user(username="trial-admin", password="test-password")
        self.admin = SchoolMembership.objects.create(
            school=self.school, user=admin_user, role=SchoolMembership.Role.SCHOOL_ADMIN,
        )
        self.plan = LicensePlan.objects.get(code=LicensePlan.Code.STANDARD)
        self.today = timezone.localdate()

    def _license(self, *, status, current_period_end, school=None):
        return SchoolLicense.objects.create(
            school=school or self.school, plan=self.plan, status=status,
            current_period_start=self.today - timedelta(days=11),
            current_period_end=current_period_end,
        )

    def test_reminds_admin_of_a_trial_ending_soon(self):
        license = self._license(status=SchoolLicense.Status.TRIAL, current_period_end=self.today + timedelta(days=2))

        result = check_trial_statuses()

        self.assertEqual(result["reminded"], 1)
        notification = Notification.objects.get(recipient=self.admin, kind=Notification.Kind.BILLING)
        self.assertIn("ending soon", notification.title.lower())
        license.refresh_from_db()
        self.assertEqual(license.status, SchoolLicense.Status.TRIAL)

    def test_moves_an_ended_trial_to_past_due_and_notifies(self):
        license = self._license(status=SchoolLicense.Status.TRIAL, current_period_end=self.today - timedelta(days=1))

        result = check_trial_statuses()

        self.assertEqual(result["expired"], 1)
        license.refresh_from_db()
        self.assertEqual(license.status, SchoolLicense.Status.PAST_DUE)
        notification = Notification.objects.get(recipient=self.admin, kind=Notification.Kind.BILLING)
        self.assertIn("ended", notification.title.lower())

    def test_does_not_touch_active_or_already_past_due_licenses(self):
        other_school = School.objects.create(name="Other Trial School", slug="other-trial-school")
        self._license(status=SchoolLicense.Status.ACTIVE, current_period_end=self.today + timedelta(days=1))
        self._license(
            status=SchoolLicense.Status.PAST_DUE, current_period_end=self.today - timedelta(days=5),
            school=other_school,
        )

        result = check_trial_statuses()

        self.assertEqual(result, {"reminded": 0, "expired": 0})
        self.assertFalse(Notification.objects.exists())

    def test_running_twice_does_not_duplicate_notifications(self):
        self._license(status=SchoolLicense.Status.TRIAL, current_period_end=self.today + timedelta(days=1))

        check_trial_statuses()
        check_trial_statuses()

        self.assertEqual(Notification.objects.filter(kind=Notification.Kind.BILLING).count(), 1)

    def test_management_command_reports_counts(self):
        self._license(status=SchoolLicense.Status.TRIAL, current_period_end=self.today - timedelta(days=1))

        out = StringIO()
        call_command("check_trial_status", stdout=out)

        self.assertIn("1 trial(s) to past-due", out.getvalue())
