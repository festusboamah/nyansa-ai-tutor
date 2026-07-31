from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from courses.models import Enrollment, Subject
from schools.models import School, SchoolMembership

from .models import Assignment, AssignmentSubmission, Quiz, Submission


class AssessmentModelTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher", password="test-password", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(username="student", password="test-password")
        self.school = School.objects.create(name="Assessment School", slug="assessment-school")
        SchoolMembership.objects.create(
            school=self.school, user=self.student, role=SchoolMembership.Role.STUDENT
        )
        SchoolMembership.objects.create(
            school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER
        )
        self.subject = Subject.objects.create(school=self.school, name="English")

    def test_quiz_defaults_remain_stable(self):
        quiz = Quiz.objects.create(subject=self.subject, teacher=self.teacher, title="Grammar")

        self.assertEqual(quiz.assessment_type, Quiz.AssessmentType.QUIZ)
        self.assertEqual(quiz.time_limit_minutes, 15)
        self.assertEqual(quiz.max_attempts, 2)
        self.assertFalse(quiz.is_past_deadline())

    def test_assignment_is_ungraded_until_teacher_sets_final_score(self):
        assignment = Assignment.objects.create(
            subject=self.subject, teacher=self.teacher, title="Essay"
        )
        submission = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=self.student,
            file="assignment_submissions/essay.pdf",
            ai_suggested_score=82,
        )

        self.assertFalse(submission.is_graded())
        submission.final_score = 80
        submission.save(update_fields=["final_score"])
        self.assertTrue(submission.is_graded())


class AssessmentAccessBaselineTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher", password="test-password", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(username="student", password="test-password")
        self.other_student = User.objects.create_user(
            username="other-student", password="test-password"
        )
        self.school = School.objects.create(name="Quiz School", slug="quiz-school")
        for student in (self.student, self.other_student):
            SchoolMembership.objects.create(
                school=self.school, user=student, role=SchoolMembership.Role.STUDENT
            )
        SchoolMembership.objects.create(
            school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER
        )
        self.subject = Subject.objects.create(school=self.school, name="Social Studies")
        Enrollment.objects.create(student=self.student, subject=self.subject)
        self.quiz = Quiz.objects.create(
            subject=self.subject, teacher=self.teacher, title="Citizenship"
        )

    def test_student_cannot_open_another_students_result(self):
        submission = Submission.objects.create(quiz=self.quiz, student=self.student, score=75)
        self.client.force_login(self.other_student)

        response = self.client.get(
            reverse("quiz_result", args=[submission.id]), secure=True
        )

        self.assertEqual(response.status_code, 404)

    def test_student_cannot_open_quiz_creation(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("create_quiz"), secure=True)

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
