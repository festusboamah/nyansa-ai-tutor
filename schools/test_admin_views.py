from datetime import date
from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from academics.models import AcademicYear
from .forms import TermForm
from .models import School, SchoolMembership
from .models import SchoolInvitation
from .services import accept_invitation, create_invitation
from django.core.exceptions import PermissionDenied


class SchoolAdminViewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Admin School", slug="admin-school")
        self.other_school = School.objects.create(name="Other School", slug="other-school")
        self.admin_user = User.objects.create_user(username="administrator", password="test-password")
        SchoolMembership.objects.create(school=self.school, user=self.admin_user, role=SchoolMembership.Role.SCHOOL_ADMIN)
        self.student = User.objects.create_user(username="student-admin-test", password="test-password")
        SchoolMembership.objects.create(school=self.school, user=self.student, role=SchoolMembership.Role.STUDENT)

    def test_school_admin_can_open_dashboard(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("school_admin_dashboard"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.school.name)

    def test_student_cannot_open_admin_dashboard(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("school_admin_dashboard"), secure=True)
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_admin_can_create_academic_year_for_active_school(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse("create_academic_year"), {
            "name": "2026/2027", "start_date": "2026-09-01", "end_date": "2027-07-31", "is_current": "on",
        }, secure=True)
        self.assertRedirects(response, reverse("school_admin_dashboard"), fetch_redirect_response=False)
        self.assertTrue(AcademicYear.objects.filter(school=self.school, name="2026/2027").exists())

    def test_term_form_excludes_other_schools_years(self):
        own = AcademicYear.objects.create(school=self.school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 7, 31))
        AcademicYear.objects.create(school=self.other_school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 7, 31))
        form = TermForm(school=self.school)
        self.assertQuerySetEqual(form.fields["academic_year"].queryset, [own])

    def test_admin_can_create_class_for_active_school(self):
        year = AcademicYear.objects.create(school=self.school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 7, 31))
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse("create_school_class"), {
            "academic_year": year.id, "name": "JHS 1", "capacity": 35,
        }, secure=True)
        self.assertRedirects(response, reverse("school_admin_dashboard"), fetch_redirect_response=False)
        self.assertTrue(self.school.classes.filter(name="JHS 1").exists())

    def test_admin_can_invite_member_without_storing_raw_token(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse("invite_member"), {
            "email": "teacher@example.com", "role": SchoolMembership.Role.TEACHER,
        }, secure=True)
        self.assertRedirects(response, reverse("people_directory"), fetch_redirect_response=False)
        invitation = SchoolInvitation.objects.get(email="teacher@example.com")
        self.assertEqual(len(invitation.token_digest), 64)
        self.assertNotIn(invitation.token_digest.encode(), response.content)

    def test_admin_cannot_suspend_member_from_another_school(self):
        other_user = User.objects.create_user(username="other-member", password="test-password")
        membership = SchoolMembership.objects.create(school=self.other_school, user=other_user, role=SchoolMembership.Role.STUDENT)
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse("set_membership_status", args=[membership.id, "SUSPENDED"]), secure=True)
        self.assertEqual(response.status_code, 404)
        membership.refresh_from_db()
        self.assertEqual(membership.status, SchoolMembership.Status.ACTIVE)

    def test_matching_user_can_accept_invitation_once(self):
        user = User.objects.create_user(username="invitee", email="invitee@example.com", password="test-password")
        invitation, token = create_invitation(school=self.school, email=user.email, role=SchoolMembership.Role.PARENT, invited_by=self.admin_user)
        membership = accept_invitation(raw_token=token, user=user)
        self.assertEqual(membership.role, SchoolMembership.Role.PARENT)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, SchoolInvitation.Status.ACCEPTED)
        with self.assertRaises(PermissionDenied):
            accept_invitation(raw_token=token, user=user)

    def test_invitation_rejects_different_email(self):
        user = User.objects.create_user(username="wrong-user", email="wrong@example.com", password="test-password")
        _invitation, token = create_invitation(school=self.school, email="right@example.com", role=SchoolMembership.Role.STUDENT, invited_by=self.admin_user)
        with self.assertRaises(PermissionDenied):
            accept_invitation(raw_token=token, user=user)
