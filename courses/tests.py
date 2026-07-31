from django.test import TestCase
from django.db import IntegrityError
from django.urls import reverse

from accounts.models import User
from quizzes.models import Assignment, AssignmentSubmission, Quiz, Submission

from .grading import calculate_subject_grade, letter_grade
from .models import Enrollment, Subject


class LetterGradeTests(TestCase):
    def test_grade_boundaries(self):
        cases = [
            (None, "N/A"),
            (0, "F"),
            (49.9, "F"),
            (50, "D"),
            (60, "C"),
            (70, "B"),
            (80, "A"),
            (100, "A"),
        ]

        for score, expected in cases:
            with self.subTest(score=score):
                self.assertEqual(letter_grade(score), expected)


class SubjectGradeTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="student", password="test-password")
        self.teacher = User.objects.create_user(
            username="teacher", password="test-password", role=User.Role.TEACHER
        )
        self.subject = Subject.objects.create(name="Mathematics")

    def test_weighted_grade_uses_quiz_assignment_and_exam_weights(self):
        quiz = Quiz.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            title="Fractions Quiz",
            assessment_type=Quiz.AssessmentType.QUIZ,
        )
        exam = Quiz.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            title="End of Term Exam",
            assessment_type=Quiz.AssessmentType.EXAM,
        )
        assignment = Assignment.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            title="Number Project",
        )
        Submission.objects.create(quiz=quiz, student=self.student, score=80)
        Submission.objects.create(quiz=exam, student=self.student, score=70)
        AssignmentSubmission.objects.create(
            assignment=assignment,
            student=self.student,
            file="assignment_submissions/test.pdf",
            final_score=90,
        )

        result = calculate_subject_grade(self.student, self.subject)

        self.assertEqual(result["quiz_avg"], 80)
        self.assertEqual(result["assignment_avg"], 90)
        self.assertEqual(result["exam_avg"], 70)
        self.assertEqual(result["final_score"], 76)
        self.assertEqual(result["final_grade"], "B")

    def test_missing_categories_are_reweighted(self):
        quiz = Quiz.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            title="Only Quiz",
            assessment_type=Quiz.AssessmentType.QUIZ,
        )
        Submission.objects.create(quiz=quiz, student=self.student, score=73)

        result = calculate_subject_grade(self.student, self.subject)

        self.assertEqual(result["final_score"], 73)
        self.assertEqual(result["final_grade"], "B")

    def test_no_results_returns_no_final_score(self):
        result = calculate_subject_grade(self.student, self.subject)

        self.assertIsNone(result["final_score"])
        self.assertEqual(result["final_grade"], "N/A")


class EnrollmentConstraintTests(TestCase):
    def test_student_cannot_enroll_in_same_subject_twice(self):
        student = User.objects.create_user(username="duplicate-test", password="test-password")
        subject = Subject.objects.create(name="Constraint Science")
        Enrollment.objects.create(student=student, subject=subject)

        with self.assertRaises(IntegrityError):
            Enrollment.objects.create(student=student, subject=subject)


class CourseAccessBaselineTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="student", password="test-password")
        self.teacher = User.objects.create_user(
            username="teacher", password="test-password", role=User.Role.TEACHER
        )
        self.subject = Subject.objects.create(name="Science")

    def test_student_cannot_create_subject(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("create_subject"), secure=True)

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_unenrolled_student_cannot_open_subject(self):
        self.client.force_login(self.student)

        response = self.client.get(
            reverse("subject_detail", args=[self.subject.id]), secure=True
        )

        self.assertRedirects(
            response, reverse("browse_subjects"), fetch_redirect_response=False
        )

    def test_enrolled_student_can_open_subject(self):
        Enrollment.objects.create(student=self.student, subject=self.subject)
        self.client.force_login(self.student)

        response = self.client.get(
            reverse("subject_detail", args=[self.subject.id]), secure=True
        )

        self.assertEqual(response.status_code, 200)
