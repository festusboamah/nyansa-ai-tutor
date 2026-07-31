from datetime import date
from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from academics.models import AcademicYear
from .forms import TermForm
from .models import School, SchoolMembership


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
