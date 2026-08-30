from datetime import date

from django.test import TestCase
from django.urls import reverse

from academics.models import (
    AcademicYear,
    ClassEnrollment,
    SchoolClass,
    SubjectOffering,
    TeacherAssignment,
    Term,
)
from accounts.models import User
from courses.models import Enrollment, Subject
from schools.models import School, SchoolMembership

from .models import Question, Quiz


class PlainQuizOfferingRestrictionTests(TestCase):
    """
    Covers a teacher who teaches the same subject to more than one class
    (e.g. English Language to both General Arts 1 and General Arts 2), and
    wants a particular quiz to go to only one of those classes instead of
    every student enrolled in the subject.
    """

    def setUp(self):
        self.school = School.objects.create(name="Offering School", slug="offering-school")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027",
            start_date=date(2026, 9, 1), end_date=date(2027, 7, 31), is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", order=1,
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15),
        )
        self.subject = Subject.objects.create(school=self.school, name="English Language")

        self.class_a = SchoolClass.objects.create(school=self.school, academic_year=self.year, name="General Arts 1")
        self.class_b = SchoolClass.objects.create(school=self.school, academic_year=self.year, name="General Arts 2")
        self.offering_a = SubjectOffering.objects.create(
            school=self.school, school_class=self.class_a, subject=self.subject, term=self.term,
        )
        self.offering_b = SubjectOffering.objects.create(
            school=self.school, school_class=self.class_b, subject=self.subject, term=self.term,
        )

        self.teacher_user = User.objects.create_user(
            username="teacher", password="test-password", role=User.Role.TEACHER
        )
        self.teacher_membership = SchoolMembership.objects.create(
            school=self.school, user=self.teacher_user, role=SchoolMembership.Role.TEACHER
        )
        TeacherAssignment.objects.create(offering=self.offering_a, teacher=self.teacher_membership)
        TeacherAssignment.objects.create(offering=self.offering_b, teacher=self.teacher_membership)

        self.student_a_user = User.objects.create_user(username="student-a", password="test-password")
        self.student_a = SchoolMembership.objects.create(
            school=self.school, user=self.student_a_user, role=SchoolMembership.Role.STUDENT
        )
        ClassEnrollment.objects.create(school_class=self.class_a, student=self.student_a)

        self.student_b_user = User.objects.create_user(username="student-b", password="test-password")
        self.student_b = SchoolMembership.objects.create(
            school=self.school, user=self.student_b_user, role=SchoolMembership.Role.STUDENT
        )
        ClassEnrollment.objects.create(school_class=self.class_b, student=self.student_b)

        # Joining a class auto-enrols a student in the class's subjects (academics/signals.py),
        # so both students are enrolled in "English Language" despite being in different classes.
        self.assertTrue(Enrollment.objects.filter(student=self.student_a_user, subject=self.subject).exists())
        self.assertTrue(Enrollment.objects.filter(student=self.student_b_user, subject=self.subject).exists())

        self.quiz = Quiz.objects.create(
            subject=self.subject, teacher=self.teacher_user, title="Grammar Check",
            assessment_type=Quiz.AssessmentType.QUIZ, status=Quiz.Status.PUBLISHED,
            time_limit_minutes=20, max_attempts=1,
        )
        Question.objects.create(
            quiz=self.quiz, text="Pick the noun.", question_type=Question.QuestionType.MULTIPLE_CHOICE,
            points=1, order=1,
        )

    def test_unrestricted_quiz_is_open_to_every_enrolled_student_regardless_of_class(self):
        for user in (self.student_a_user, self.student_b_user):
            self.client.force_login(user)
            response = self.client.get(reverse("quiz_start", args=[self.quiz.id]), secure=True)
            self.assertEqual(response.status_code, 200)

    def test_restricting_to_one_class_blocks_a_student_from_the_other_class(self):
        self.quiz.offerings.add(self.offering_a)

        self.client.force_login(self.student_b_user)
        response = self.client.get(reverse("quiz_start", args=[self.quiz.id]), secure=True, follow=True)

        self.assertContains(response, "This quiz is restricted to a class you are not part of.")

    def test_restricting_to_one_class_still_allows_that_classs_student(self):
        self.quiz.offerings.add(self.offering_a)

        self.client.force_login(self.student_a_user)
        response = self.client.get(reverse("quiz_start", args=[self.quiz.id]), secure=True)

        self.assertEqual(response.status_code, 200)

    def test_take_view_also_enforces_the_restriction(self):
        self.quiz.offerings.add(self.offering_a)

        self.client.force_login(self.student_b_user)
        response = self.client.get(reverse("quiz_take", args=[self.quiz.id]), secure=True, follow=True)

        self.assertContains(response, "This quiz is restricted to a class you are not part of.")

    def test_restricted_quiz_is_hidden_from_the_other_classs_student_on_the_subject_page(self):
        self.quiz.offerings.add(self.offering_a)

        self.client.force_login(self.student_b_user)
        response = self.client.get(reverse("subject_detail", args=[self.subject.id]), secure=True)

        self.assertNotContains(response, "Grammar Check")

        self.client.force_login(self.student_a_user)
        response = self.client.get(reverse("subject_detail", args=[self.subject.id]), secure=True)

        self.assertContains(response, "Grammar Check")

    def test_teacher_can_restrict_a_plain_quiz_via_choose_classes(self):
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            reverse("select_exam_offerings", args=[self.quiz.id]),
            {"offerings": [self.offering_a.id]},
            secure=True,
        )

        self.assertRedirects(response, reverse("add_question", args=[self.quiz.id]), fetch_redirect_response=False)
        self.assertEqual(list(self.quiz.offerings.all()), [self.offering_a])

    def test_teacher_can_clear_the_restriction_back_to_subject_wide(self):
        self.quiz.offerings.add(self.offering_a)
        self.client.force_login(self.teacher_user)

        response = self.client.post(
            reverse("select_exam_offerings", args=[self.quiz.id]), {"offerings": []}, secure=True,
        )

        self.assertRedirects(response, reverse("add_question", args=[self.quiz.id]), fetch_redirect_response=False)
        self.assertEqual(self.quiz.offerings.count(), 0)
