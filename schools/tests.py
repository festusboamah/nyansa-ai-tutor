from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.contrib.sessions.middleware import SessionMiddleware

from courses.models import Subject
from academics.models import AcademicYear, ClassEnrollment, SchoolClass

from .models import School, SchoolMembership
from .services import (
    ACTIVE_SCHOOL_SESSION_KEY,
    resolve_active_membership,
    scope_to_school,
    select_active_school,
)


User = get_user_model()


def request_with_session(user):
    request = RequestFactory().get("/")
    SessionMiddleware(lambda current_request: None).process_request(request)
    request.session.save()
    request.user = user
    return request


class SchoolMembershipTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", password="test-password")
        self.school = School.objects.create(name="Nyansa Academy", slug="nyansa-academy")

    def test_membership_is_unique_per_school_and_user(self):
        SchoolMembership.objects.create(
            school=self.school,
            user=self.user,
            role=SchoolMembership.Role.STUDENT,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            SchoolMembership.objects.create(
                school=self.school, user=self.user, role=SchoolMembership.Role.PARENT
            )

    def test_suspended_membership_is_not_active(self):
        membership = SchoolMembership.objects.create(
            school=self.school,
            user=self.user,
            role=SchoolMembership.Role.TEACHER,
            status=SchoolMembership.Status.SUSPENDED,
        )

        self.assertFalse(membership.is_active)


class SchoolOnboardingTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Setup School", slug="setup-school")
        self.admin_user = User.objects.create_user(username="setup-admin", password="test-password")
        self.admin = SchoolMembership.objects.create(
            school=self.school, user=self.admin_user, role=SchoolMembership.Role.SCHOOL_ADMIN
        )
        self.client.force_login(self.admin_user)

    def test_admin_can_open_guided_setup(self):
        response = self.client.get(reverse("school_onboarding"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Set up Setup School")
        self.assertContains(response, "Enrol students")

    def test_subject_step_creates_school_scoped_subject(self):
        response = self.client.post(reverse("school_onboarding"), {
            "step": "subject", "name": "Integrated Science", "description": "Core subject",
        }, secure=True)
        self.assertEqual(response.status_code, 302)
        subject = Subject.objects.get(name="Integrated Science")
        self.assertEqual(subject.school, self.school)
        self.assertIn("?step=offering", response.url)

    def test_profile_save_advances_to_academic_year(self):
        response = self.client.post(reverse("school_onboarding"), {
            "step": "profile", "name": self.school.name, "address": "Accra",
            "phone": "0200000000", "email": "setup@example.com", "timezone": "Africa/Accra",
        }, secure=True)
        self.assertRedirects(
            response, f"{reverse('school_onboarding')}?step=year", fetch_redirect_response=False
        )

    def test_new_current_year_replaces_previous_current_year(self):
        previous = AcademicYear.objects.create(
            school=self.school, name="2025/2026", start_date="2025-09-01",
            end_date="2026-07-31", is_current=True,
        )
        response = self.client.post(reverse("school_onboarding"), {
            "step": "year", "name": "2026/2027", "start_date": "2026-09-01",
            "end_date": "2027-07-31", "is_current": "on",
        }, secure=True)
        self.assertEqual(response.status_code, 302)
        previous.refresh_from_db()
        self.assertFalse(previous.is_current)
        self.assertTrue(AcademicYear.objects.get(name="2026/2027").is_current)

    def test_duplicate_year_shows_form_error_instead_of_server_error(self):
        AcademicYear.objects.create(
            school=self.school, name="2026/2027", start_date="2026-09-01", end_date="2027-07-31"
        )
        response = self.client.post(reverse("school_onboarding"), {
            "step": "year", "name": "2026/2027", "start_date": "2026-09-01",
            "end_date": "2027-07-31",
        }, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_term_step_stays_open_until_three_terms_exist(self):
        year = AcademicYear.objects.create(
            school=self.school, name="2026/2027", start_date="2026-09-01", end_date="2027-07-31"
        )
        term_dates = [
            ("First Term", 1, "2026-09-01", "2026-12-18"),
            ("Second Term", 2, "2027-01-11", "2027-04-09"),
            ("Third Term", 3, "2027-04-26", "2027-07-31"),
        ]
        for index, (name, order, start, end) in enumerate(term_dates):
            response = self.client.post(reverse("school_onboarding"), {
                "step": "term", "academic_year": year.id, "name": name,
                "order": order, "start_date": start, "end_date": end,
            }, secure=True)
            expected = "people" if index == 2 else "term"
            self.assertIn(f"?step={expected}", response.url)

    def test_enrollment_step_rejects_student_from_another_school(self):
        year = AcademicYear.objects.create(
            school=self.school, name="2026/27", start_date="2026-09-01", end_date="2027-07-31"
        )
        school_class = SchoolClass.objects.create(school=self.school, academic_year=year, name="Basic 5")
        other_school = School.objects.create(name="Other Setup School", slug="other-setup-school")
        other_user = User.objects.create_user(username="outside-student", password="test-password")
        outside_student = SchoolMembership.objects.create(
            school=other_school, user=other_user, role=SchoolMembership.Role.STUDENT
        )
        response = self.client.post(reverse("school_onboarding"), {
            "step": "enrollment", "school_class": school_class.id, "student": outside_student.id,
        }, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertFalse(ClassEnrollment.objects.exists())


class ActiveSchoolResolutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teacher", password="test-password")
        self.school_a = School.objects.create(name="School A", slug="school-a")
        self.school_b = School.objects.create(name="School B", slug="school-b")

    def test_single_membership_is_selected_automatically(self):
        membership = SchoolMembership.objects.create(
            school=self.school_a,
            user=self.user,
            role=SchoolMembership.Role.TEACHER,
        )
        request = request_with_session(self.user)

        resolved = resolve_active_membership(request)

        self.assertEqual(resolved, membership)
        self.assertEqual(request.session[ACTIVE_SCHOOL_SESSION_KEY], self.school_a.id)

    def test_multiple_memberships_require_explicit_selection(self):
        SchoolMembership.objects.create(
            school=self.school_a, user=self.user, role=SchoolMembership.Role.TEACHER
        )
        SchoolMembership.objects.create(
            school=self.school_b, user=self.user, role=SchoolMembership.Role.TEACHER
        )
        request = request_with_session(self.user)

        self.assertIsNone(resolve_active_membership(request))

    def test_user_cannot_select_school_without_membership(self):
        request = request_with_session(self.user)

        with self.assertRaises(PermissionDenied):
            select_active_school(request, self.school_b)


class TenantScopingTests(TestCase):
    def test_subject_query_never_returns_another_schools_rows(self):
        school_a = School.objects.create(name="School A", slug="school-a")
        school_b = School.objects.create(name="School B", slug="school-b")
        subject_a = Subject.objects.create(school=school_a, name="Mathematics")
        Subject.objects.create(school=school_b, name="Mathematics")

        result = scope_to_school(Subject.objects.all(), school_a)

        self.assertQuerySetEqual(result, [subject_a])

    def test_missing_school_context_returns_no_rows(self):
        school = School.objects.create(name="School A", slug="school-a")
        Subject.objects.create(school=school, name="Science")

        self.assertFalse(scope_to_school(Subject.objects.all(), None).exists())
