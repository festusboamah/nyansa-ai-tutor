from django.db import IntegrityError
from django.test import TestCase

from accounts.models import User
from courses.grading import calculate_subject_grade, letter_grade
from courses.models import Enrollment, Subject
from quizzes.models import Assignment, AssignmentSubmission, Quiz, Submission


class GradingTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="student", password="test-password")
        self.teacher = User.objects.create_user(
            username="teacher", password="test-password", role=User.Role.TEACHER
        )
        self.subject = Subject.objects.create(name="Mathematics")

    def test_calculates_weighted_grade_from_available_categories(self):
        quiz = Quiz.objects.create(subject=self.subject, teacher=self.teacher, title="Quiz")
        exam = Quiz.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            title="Exam",
            assessment_type=Quiz.AssessmentType.EXAM,
        )
        assignment = Assignment.objects.create(subject=self.subject, teacher=self.teacher, title="Assignment")
        Submission.objects.create(quiz=quiz, student=self.student, score=80)
        Submission.objects.create(quiz=exam, student=self.student, score=90)
        AssignmentSubmission.objects.create(
            assignment=assignment,
            student=self.student,
            file="assignment_submissions/work.pdf",
            final_score=70,
        )

        grade = calculate_subject_grade(self.student, self.subject)

        self.assertEqual(grade["final_score"], 84.0)
        self.assertEqual(grade["final_grade"], "A")

    def test_reweights_grade_when_only_one_category_is_graded(self):
        quiz = Quiz.objects.create(subject=self.subject, teacher=self.teacher, title="Quiz")
        Submission.objects.create(quiz=quiz, student=self.student, score=75)

        grade = calculate_subject_grade(self.student, self.subject)

        self.assertEqual(grade["final_score"], 75.0)
        self.assertEqual(grade["final_grade"], "B")

    def test_letter_grades_cover_boundaries(self):
        self.assertEqual(letter_grade(None), "N/A")
        self.assertEqual(letter_grade(80), "A")
        self.assertEqual(letter_grade(70), "B")
        self.assertEqual(letter_grade(60), "C")
        self.assertEqual(letter_grade(50), "D")
        self.assertEqual(letter_grade(49.9), "F")


class EnrollmentTests(TestCase):
    def test_student_cannot_be_enrolled_in_same_subject_twice(self):
        student = User.objects.create_user(username="student", password="test-password")
        subject = Subject.objects.create(name="Science")
        Enrollment.objects.create(student=student, subject=subject)

        with self.assertRaises(IntegrityError):
            Enrollment.objects.create(student=student, subject=subject)
