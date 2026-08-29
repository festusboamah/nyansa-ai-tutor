from django.test import TestCase
from django.urls import reverse

from schools.models import School, SchoolMembership

from .forms import SchoolAdminSignUpForm, StudentSignUpForm
from .models import User


class UserRoleTests(TestCase):
    def test_new_user_defaults_to_student(self):
        user = User.objects.create_user(username="ama", password="safe-test-password")

        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertTrue(user.is_student())
        self.assertFalse(user.is_teacher())

    def test_teacher_helpers_reflect_role(self):
        teacher = User.objects.create_user(
            username="kwame",
            password="safe-test-password",
            role=User.Role.TEACHER,
        )

        self.assertTrue(teacher.is_teacher())
        self.assertFalse(teacher.is_student())


class StudentSignupTests(TestCase):
    def test_signup_form_assigns_student_role(self):
        form = StudentSignUpForm(
            data={
                "username": "esi",
                "email": "esi@example.com",
                "password1": "A-long-test-password-2026",
                "password2": "A-long-test-password-2026",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertEqual(user.email, "esi@example.com")

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse("profile"), secure=True)

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('profile')}",
            fetch_redirect_response=False,
        )


class SchoolAdminSignupTests(TestCase):
    def test_signup_form_creates_school_and_admin_membership(self):
        form = SchoolAdminSignUpForm(
            data={
                "username": "headteacher",
                "email": "head@example.com",
                "school_name": "Nyansa Model School",
                "password1": "A-long-test-password-2026",
                "password2": "A-long-test-password-2026",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        school = School.objects.get(name="Nyansa Model School")
        self.assertEqual(school.slug, "nyansa-model-school")
        membership = SchoolMembership.objects.get(school=school, user=user)
        self.assertEqual(membership.role, SchoolMembership.Role.SCHOOL_ADMIN)
        self.assertTrue(membership.is_active)

    def test_duplicate_school_name_gets_a_unique_slug(self):
        School.objects.create(name="Existing School", slug="existing-school")
        form = SchoolAdminSignUpForm(
            data={
                "username": "second-admin",
                "email": "second@example.com",
                "school_name": "Existing School",
                "password1": "A-long-test-password-2026",
                "password2": "A-long-test-password-2026",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.assertTrue(School.objects.filter(name="Existing School", slug="existing-school-2").exists())

    def test_school_signup_view_logs_in_and_redirects_to_onboarding(self):
        response = self.client.post(
            reverse("school_signup"),
            data={
                "username": "new-admin",
                "email": "new-admin@example.com",
                "school_name": "Fresh Start Academy",
                "password1": "A-long-test-password-2026",
                "password2": "A-long-test-password-2026",
            },
            secure=True,
        )

        self.assertRedirects(response, reverse("school_onboarding"), fetch_redirect_response=False)
        user = User.objects.get(username="new-admin")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertTrue(
            SchoolMembership.objects.filter(user=user, role=SchoolMembership.Role.SCHOOL_ADMIN).exists()
        )
