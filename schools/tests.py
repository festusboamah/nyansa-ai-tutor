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
