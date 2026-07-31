from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from courses.models import Subject
from schools.models import School, SchoolMembership

from .models import LessonNote


class LessonNoteAccessBaselineTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher", password="test-password", role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            username="other-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(username="student", password="test-password")
        self.school = School.objects.create(name="Lesson School", slug="lesson-school")
        SchoolMembership.objects.create(
            school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER
        )
        SchoolMembership.objects.create(
            school=self.school,
            user=self.other_teacher,
            role=SchoolMembership.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            school=self.school, user=self.student, role=SchoolMembership.Role.STUDENT
        )
        self.subject = Subject.objects.create(school=self.school, name="Integrated Science")
        self.note = LessonNote.objects.create(
            teacher=self.teacher,
            subject=self.subject,
            class_level="JHS 2",
            week_ending=date(2026, 7, 31),
            strand_topic="Reproduction",
            learning_indicator="Describe the stages of reproduction.",
        )

    def test_student_cannot_open_teacher_dashboard(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("teacher_dashboard"), secure=True)

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_teacher_only_sees_own_lesson_note_list(self):
        self.client.force_login(self.other_teacher)

        response = self.client.get(reverse("lesson_notes_list"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.note.strand_topic)

    def test_teacher_cannot_open_another_teachers_lesson_note(self):
        self.client.force_login(self.other_teacher)

        response = self.client.get(
            reverse("lesson_note_detail", args=[self.note.id]), secure=True
        )

        self.assertEqual(response.status_code, 404)

    def test_teacher_can_open_teacher_dashboard(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("teacher_dashboard"), secure=True)

        self.assertEqual(response.status_code, 200)
