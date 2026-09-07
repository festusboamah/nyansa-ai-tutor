from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from courses.models import Enrollment, Material, Subject
from quizzes.models import Assignment, Quiz
from schools.models import School, SchoolMembership


class LearningWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Workspace School", slug="workspace-school")
        cls.other_school = School.objects.create(name="Other School", slug="other-workspace")
        cls.teacher = User.objects.create_user(username="workspace-teacher", role=User.Role.TEACHER)
        cls.student = User.objects.create_user(username="workspace-student")
        SchoolMembership.objects.create(school=cls.school, user=cls.teacher, role="TEACHER")
        SchoolMembership.objects.create(school=cls.school, user=cls.student, role="STUDENT")
        cls.material_subject = Subject.objects.create(school=cls.school, name="Material-only subject")
        cls.quiz_subject = Subject.objects.create(school=cls.school, name="Quiz-only subject")
        cls.assignment_subject = Subject.objects.create(school=cls.school, name="Assignment-only subject")
        cls.foreign_subject = Subject.objects.create(school=cls.other_school, name="Foreign hidden subject")
        Material.objects.create(subject=cls.material_subject, teacher=cls.teacher, title="Reading")
        Quiz.objects.create(subject=cls.quiz_subject, teacher=cls.teacher, title="Practice")
        Assignment.objects.create(subject=cls.assignment_subject, teacher=cls.teacher, title="Project")
        Material.objects.create(subject=cls.foreign_subject, teacher=cls.teacher, title="Private foreign material")
        Enrollment.objects.create(subject=cls.quiz_subject, student=cls.student)

    def test_teacher_home_combines_all_owned_content_without_cross_school_leak(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("teacher_dashboard"), secure=True)
        self.assertEqual(response.status_code, 200)
        for subject in (self.material_subject, self.quiz_subject, self.assignment_subject):
            self.assertContains(response, subject.name)
        self.assertNotContains(response, self.foreign_subject.name)
        self.assertContains(response, "Teacher Copilot")
        self.assertContains(response, reverse("create_content"))

    def test_student_home_hides_draft_deadlines_and_other_subjects(self):
        Quiz.objects.create(subject=self.quiz_subject, teacher=self.teacher, title="Private draft quiz", status="DRAFT", deadline=timezone.now() + timedelta(days=1))
        Quiz.objects.create(subject=self.quiz_subject, teacher=self.teacher, title="Upcoming public quiz", deadline=timezone.now() + timedelta(days=2))
        self.client.force_login(self.student)
        response = self.client.get(reverse("dashboard"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upcoming public quiz")
        self.assertNotContains(response, "Private draft quiz")
        self.assertNotContains(response, self.foreign_subject.name)
        self.assertNotContains(response, self.assignment_subject.name)
        self.assertContains(response, 'data-search-input')

    def test_student_cannot_enter_teacher_workspace(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("teacher_dashboard"), secure=True)
        self.assertEqual(response.status_code, 302)

    def test_catalog_escapes_subject_names_and_keeps_post_csrf_enrolment(self):
        subject = Subject.objects.create(school=self.school, name='<script>alert("x")</script>')
        self.client.force_login(self.student)
        response = self.client.get(reverse("browse_subjects"), secure=True)
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, subject.name)
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertContains(response, 'method="post"')
        self.assertNotContains(response, self.foreign_subject.name)

    def test_enrolled_subject_keeps_material_assessment_and_assignment_sections(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("subject_detail", args=[self.quiz_subject.id]), secure=True)
        self.assertEqual(response.status_code, 200)
        for anchor in ('id="materials"', 'id="quizzes"', 'id="assignments"'):
            self.assertContains(response, anchor)

    def test_tutor_form_keeps_all_grounding_fields_and_csrf(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("tutor_home"), secure=True)
        self.assertEqual(response.status_code, 200)
        for field in ("mode", "subject_id", "document_id", "material_id", "topic_id"):
            self.assertContains(response, f'name="{field}"')
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertContains(response, 'Start tutoring session')

    def test_study_library_empty_state(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("study_documents"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Give your ideas a home.")
        self.assertContains(response, reverse("upload_study_document"))
