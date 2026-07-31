from django.test import TestCase
from django.urls import reverse

from .forms import StudentSignUpForm
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
