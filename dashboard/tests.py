from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class TeacherDashboardAccessTests(TestCase):
    def test_student_is_redirected_from_teacher_dashboard(self):
        student = User.objects.create_user(username="student", password="test-password")
        self.client.force_login(student)

        response = self.client.get(reverse("teacher_dashboard"))

        self.assertRedirects(response, reverse("home"))

    def test_teacher_can_open_teacher_dashboard(self):
        teacher = User.objects.create_user(
            username="teacher", password="test-password", role=User.Role.TEACHER
        )
        self.client.force_login(teacher)

        response = self.client.get(reverse("teacher_dashboard"))

        self.assertEqual(response.status_code, 200)
