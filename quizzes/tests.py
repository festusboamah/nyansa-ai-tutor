from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from courses.models import Enrollment, Subject
from mastery.models import Strand, Topic
from schools.models import School, SchoolMembership

from . import ai_grading, ai_quiz_generator, assignment_ai
from .models import (
    Answer,
    Assignment,
    AssignmentSubmission,
    BankQuestion,
    Choice,
    CriterionScore,
    Question,
    Quiz,
    QuizGenerationSettings,
    RubricCriterion,
    Submission,
)


def _fake_response(text):
    return Mock(content=[Mock(text=text)])


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


class QuizAIHelpersTests(TestCase):
    @patch("ai_core.client.client")
    def test_generate_quiz_questions_returns_parsed_list_on_success(self, mock_client):
        mock_client.messages.create.return_value = _fake_response('{"questions": [{"text": "2+2?"}]}')
        result = ai_quiz_generator.generate_quiz_questions("Math", 1, "easy")
        self.assertEqual(result, [{"text": "2+2?"}])

    @patch("ai_core.client.client")
    def test_generate_quiz_questions_falls_back_to_empty_list(self, mock_client):
        mock_client.messages.create.side_effect = RuntimeError("down")
        self.assertEqual(ai_quiz_generator.generate_quiz_questions("Math", 1, "easy"), [])

    @patch("ai_core.client.client")
    def test_grade_short_answer_returns_parsed_result_on_success(self, mock_client):
        mock_client.messages.create.return_value = _fake_response('{"is_correct": true, "feedback": "Nice work."}')
        result = ai_grading.grade_short_answer("What is 2+2?", "4")
        self.assertEqual(result, {"is_correct": True, "feedback": "Nice work."})

    @patch("ai_core.client.client")
    def test_grade_short_answer_falls_back_on_ai_failure(self, mock_client):
        mock_client.messages.create.side_effect = RuntimeError("down")
        result = ai_grading.grade_short_answer("What is 2+2?", "4")
        self.assertIsNone(result["is_correct"])
        self.assertIn("teacher will review", result["feedback"])

    @patch("ai_core.client.client")
    def test_generate_submission_feedback_returns_text_on_success(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("Well done overall.")
        result = ai_grading.generate_submission_feedback("Quiz 1", 80, ["Q1: correct"])
        self.assertEqual(result, "Well done overall.")

    @patch("ai_core.client.client")
    def test_generate_submission_feedback_falls_back_on_ai_failure(self, mock_client):
        mock_client.messages.create.side_effect = RuntimeError("down")
        result = ai_grading.generate_submission_feedback("Quiz 1", 80, ["Q1: correct"])
        self.assertIn("Great effort", result)

    @patch("ai_core.client.client")
    def test_suggest_assignment_grade_returns_parsed_result_on_success(self, mock_client):
        mock_client.messages.create.return_value = _fake_response(
            '{"criteria": [{"score": 90, "feedback": "Solid work."}], "overall_feedback": "Good overall."}'
        )
        criteria = [SimpleNamespace(name="Clarity", description="Is it clear?", max_points=100)]
        result = assignment_ai.suggest_assignment_grade("Essay", "Write about X", criteria, "student text", 100)
        self.assertEqual(result, {
            "criteria": [{"score": 90, "feedback": "Solid work."}], "overall_feedback": "Good overall.",
        })

    @patch("ai_core.client.client")
    def test_suggest_assignment_grade_falls_back_on_ai_failure(self, mock_client):
        mock_client.messages.create.side_effect = RuntimeError("down")
        criteria = [SimpleNamespace(name="Clarity", description="Is it clear?", max_points=100)]
        result = assignment_ai.suggest_assignment_grade("Essay", "Write about X", criteria, "student text", 100)
        self.assertIsNone(result["criteria"][0]["score"])
        self.assertIn("AI suggestion unavailable", result["overall_feedback"])


class QuizGenerationReviewTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="review-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            username="other-review-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(username="review-student", password="test-password")
        self.school = School.objects.create(name="Review School", slug="review-school")
        SchoolMembership.objects.create(school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(
            school=self.school, user=self.other_teacher, role=SchoolMembership.Role.TEACHER
        )
        SchoolMembership.objects.create(school=self.school, user=self.student, role=SchoolMembership.Role.STUDENT)
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")
        Enrollment.objects.create(student=self.student, subject=self.subject)

    def _generate(self):
        return self.client.post(reverse("ai_generate_quiz"), {
            "subject": self.subject.pk, "title": "Fractions Quiz", "topic": "Fractions",
            "num_questions": 1, "difficulty": "easy",
        }, secure=True)

    @patch("quizzes.views.generate_quiz_questions")
    def test_ai_generated_quiz_defaults_to_draft_with_no_settings_row(self, mock_generate):
        mock_generate.return_value = [{"text": "1/2 + 1/2 = ?", "choices": [
            {"text": "1", "is_correct": True}, {"text": "2", "is_correct": False},
        ]}]
        self.client.force_login(self.teacher)

        self._generate()

        quiz = Quiz.objects.get(subject=self.subject)
        self.assertEqual(quiz.status, Quiz.Status.DRAFT)

    @patch("quizzes.views.generate_quiz_questions")
    def test_ai_generated_quiz_is_published_when_review_not_required(self, mock_generate):
        QuizGenerationSettings.objects.create(school=self.school, require_review=False)
        mock_generate.return_value = [{"text": "1/2 + 1/2 = ?", "choices": [
            {"text": "1", "is_correct": True}, {"text": "2", "is_correct": False},
        ]}]
        self.client.force_login(self.teacher)

        self._generate()

        quiz = Quiz.objects.get(subject=self.subject)
        self.assertEqual(quiz.status, Quiz.Status.PUBLISHED)

    def test_student_cannot_start_a_draft_quiz(self):
        quiz = Quiz.objects.create(
            subject=self.subject, teacher=self.teacher, title="Draft Quiz", status=Quiz.Status.DRAFT,
        )
        self.client.force_login(self.student)

        response = self.client.get(reverse("quiz_start", args=[quiz.pk]), secure=True)

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_student_cannot_open_take_page_for_a_draft_quiz(self):
        quiz = Quiz.objects.create(
            subject=self.subject, teacher=self.teacher, title="Draft Quiz", status=Quiz.Status.DRAFT,
        )
        self.client.force_login(self.student)

        response = self.client.get(reverse("quiz_take", args=[quiz.pk]), secure=True)

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_student_cannot_submit_answers_for_a_draft_quiz(self):
        quiz = Quiz.objects.create(
            subject=self.subject, teacher=self.teacher, title="Draft Quiz", status=Quiz.Status.DRAFT,
        )
        question = Question.objects.create(
            quiz=quiz, text="1/2 + 1/2 = ?", question_type=Question.QuestionType.MULTIPLE_CHOICE, order=1,
        )
        Choice.objects.create(question=question, text="1", is_correct=True)
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("quiz_take", args=[quiz.pk]), {f"question_{question.id}": "1"}, secure=True
        )

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertFalse(Submission.objects.filter(quiz=quiz, student=self.student).exists())

    def test_owning_teacher_can_publish_and_student_can_then_start_it(self):
        quiz = Quiz.objects.create(
            subject=self.subject, teacher=self.teacher, title="Draft Quiz", status=Quiz.Status.DRAFT,
        )
        self.client.force_login(self.teacher)
        self.client.post(reverse("publish_quiz", args=[quiz.pk]), secure=True)

        quiz.refresh_from_db()
        self.assertEqual(quiz.status, Quiz.Status.PUBLISHED)

        self.client.force_login(self.student)
        response = self.client.get(reverse("quiz_start", args=[quiz.pk]), secure=True)
        self.assertEqual(response.status_code, 200)

    def test_other_teacher_cannot_publish_the_quiz(self):
        quiz = Quiz.objects.create(
            subject=self.subject, teacher=self.teacher, title="Draft Quiz", status=Quiz.Status.DRAFT,
        )
        self.client.force_login(self.other_teacher)

        response = self.client.post(reverse("publish_quiz", args=[quiz.pk]), secure=True)

        self.assertEqual(response.status_code, 404)
        quiz.refresh_from_db()
        self.assertEqual(quiz.status, Quiz.Status.DRAFT)

    def test_manually_created_quiz_is_published_immediately(self):
        self.client.force_login(self.teacher)

        self.client.post(reverse("create_quiz"), {
            "subject": self.subject.pk, "title": "Manual Quiz", "assessment_type": "QUIZ",
            "time_limit_minutes": 15, "max_attempts": 2,
        }, secure=True)

        quiz = Quiz.objects.get(title="Manual Quiz")
        self.assertEqual(quiz.status, Quiz.Status.PUBLISHED)

    def test_non_admin_cannot_access_quiz_generation_settings(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("quiz_generation_settings"), secure=True)
        self.assertEqual(response.status_code, 403)

    def test_admin_can_toggle_require_review(self):
        admin = User.objects.create_user(username="review-admin", password="test-password")
        SchoolMembership.objects.create(school=self.school, user=admin, role=SchoolMembership.Role.SCHOOL_ADMIN)
        self.client.force_login(admin)

        self.client.post(reverse("quiz_generation_settings"), {}, secure=True)

        settings_row = QuizGenerationSettings.objects.get(school=self.school)
        self.assertFalse(settings_row.require_review)


class QuestionBankTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="bank-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            username="other-bank-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.admin = User.objects.create_user(username="bank-admin", password="test-password")
        self.student = User.objects.create_user(username="bank-student", password="test-password")
        self.school = School.objects.create(name="Bank School", slug="bank-school")
        SchoolMembership.objects.create(school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(
            school=self.school, user=self.other_teacher, role=SchoolMembership.Role.TEACHER
        )
        SchoolMembership.objects.create(school=self.school, user=self.admin, role=SchoolMembership.Role.SCHOOL_ADMIN)
        SchoolMembership.objects.create(school=self.school, user=self.student, role=SchoolMembership.Role.STUDENT)
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.strand = Strand.objects.create(school=self.school, subject=self.subject, name="Number")
        self.topic = Topic.objects.create(strand=self.strand, name="Fractions")

        self.other_school = School.objects.create(name="Other Bank School", slug="other-bank-school")
        self.other_subject = Subject.objects.create(school=self.other_school, name="Mathematics")

    def _generate(self):
        return self.client.post(reverse("generate_bank_questions"), {
            "subject": self.subject.pk, "mastery_topic": self.topic.pk,
            "topic_description": "Adding fractions", "num_questions": 1, "difficulty": "easy",
        }, secure=True)

    def _make_bank_question(self, status=BankQuestion.Status.APPROVED, subject=None):
        bank_question = BankQuestion.objects.create(
            subject=subject or self.subject, topic=self.topic, created_by=self.teacher,
            text="1/2 + 1/2 = ?", status=status,
        )
        bank_question.choices.create(text="1", is_correct=True)
        bank_question.choices.create(text="2", is_correct=False)
        return bank_question

    @patch("quizzes.ai_quiz_generator.generate_quiz_questions")
    def test_generation_creates_pending_review_bank_questions_with_choices(self, mock_generate):
        mock_generate.return_value = [{"text": "1/2 + 1/2 = ?", "choices": [
            {"text": "1", "is_correct": True}, {"text": "2", "is_correct": False},
        ]}]
        self.client.force_login(self.teacher)

        self._generate()

        bank_question = BankQuestion.objects.get(subject=self.subject)
        self.assertEqual(bank_question.status, BankQuestion.Status.PENDING_REVIEW)
        self.assertEqual(bank_question.topic, self.topic)
        self.assertEqual(bank_question.choices.count(), 2)

    @patch("quizzes.ai_quiz_generator.generate_quiz_questions")
    def test_generation_skips_questions_missing_text_without_raising(self, mock_generate):
        mock_generate.return_value = [
            {"text": "Real question?", "choices": [
                {"text": "1", "is_correct": True}, {"text": "2", "is_correct": False},
            ]},
            {"choices": [{"text": "orphan choice", "is_correct": True}]},
        ]
        self.client.force_login(self.teacher)

        response = self._generate()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(BankQuestion.objects.filter(subject=self.subject).count(), 1)
        self.assertEqual(BankQuestion.objects.get(subject=self.subject).text, "Real question?")

    @patch("quizzes.ai_quiz_generator.generate_quiz_questions")
    def test_generation_skips_choices_missing_text(self, mock_generate):
        mock_generate.return_value = [
            {"text": "Real question?", "choices": [
                {"text": "Valid", "is_correct": True}, {"is_correct": False},
            ]},
        ]
        self.client.force_login(self.teacher)

        self._generate()

        bank_question = BankQuestion.objects.get(subject=self.subject)
        self.assertEqual(bank_question.choices.count(), 1)
        self.assertEqual(bank_question.choices.get().text, "Valid")

    def test_review_queue_lists_only_pending_questions_for_the_school(self):
        pending = self._make_bank_question(status=BankQuestion.Status.PENDING_REVIEW)
        self._make_bank_question(status=BankQuestion.Status.APPROVED)
        self._make_bank_question(status=BankQuestion.Status.PENDING_REVIEW, subject=self.other_subject)
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("bank_review_queue"), secure=True)

        self.assertContains(response, pending.text)
        self.assertEqual(response.context["pending_questions"].count(), 1)

    def test_teacher_can_approve_a_bank_question(self):
        bank_question = self._make_bank_question(status=BankQuestion.Status.PENDING_REVIEW)
        self.client.force_login(self.teacher)

        self.client.post(reverse("bank_review_queue"), {
            "bank_question_id": bank_question.pk, "action": "approve", "review_note": "Looks good",
        }, secure=True)

        bank_question.refresh_from_db()
        self.assertEqual(bank_question.status, BankQuestion.Status.APPROVED)
        self.assertEqual(bank_question.review_note, "Looks good")
        self.assertIsNotNone(bank_question.reviewed_at)

    def test_admin_can_reject_a_bank_question(self):
        bank_question = self._make_bank_question(status=BankQuestion.Status.PENDING_REVIEW)
        self.client.force_login(self.admin)

        self.client.post(reverse("bank_review_queue"), {
            "bank_question_id": bank_question.pk, "action": "reject",
        }, secure=True)

        bank_question.refresh_from_db()
        self.assertEqual(bank_question.status, BankQuestion.Status.REJECTED)

    def test_student_cannot_access_review_queue(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("bank_review_queue"), secure=True)

        self.assertEqual(response.status_code, 403)

    def test_only_approved_questions_are_selectable_for_a_quiz(self):
        approved = self._make_bank_question(status=BankQuestion.Status.APPROVED)
        self._make_bank_question(status=BankQuestion.Status.PENDING_REVIEW)
        self._make_bank_question(status=BankQuestion.Status.REJECTED)
        quiz = Quiz.objects.create(subject=self.subject, teacher=self.teacher, title="Fractions Quiz")
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("add_bank_questions", args=[quiz.pk]), secure=True)

        self.assertEqual(response.context["approved_questions"].count(), 1)
        self.assertContains(response, approved.text)

    def test_adding_a_bank_question_copies_it_into_the_quiz(self):
        bank_question = self._make_bank_question(status=BankQuestion.Status.APPROVED)
        quiz = Quiz.objects.create(subject=self.subject, teacher=self.teacher, title="Fractions Quiz")
        self.client.force_login(self.teacher)

        self.client.post(reverse("add_bank_questions", args=[quiz.pk]), {
            "bank_question_id": [bank_question.pk],
        }, secure=True)

        question = quiz.questions.get()
        self.assertEqual(question.text, bank_question.text)
        self.assertEqual(question.topic, self.topic)
        self.assertEqual(question.choices.count(), 2)
        self.assertTrue(question.choices.get(text="1").is_correct)

        # the bank question itself is untouched and reusable
        bank_question.refresh_from_db()
        self.assertEqual(bank_question.status, BankQuestion.Status.APPROVED)

    def test_the_same_bank_question_can_be_added_to_a_second_quiz(self):
        bank_question = self._make_bank_question(status=BankQuestion.Status.APPROVED)
        quiz_one = Quiz.objects.create(subject=self.subject, teacher=self.teacher, title="Quiz One")
        quiz_two = Quiz.objects.create(subject=self.subject, teacher=self.teacher, title="Quiz Two")
        self.client.force_login(self.teacher)

        self.client.post(reverse("add_bank_questions", args=[quiz_one.pk]), {
            "bank_question_id": [bank_question.pk],
        }, secure=True)
        self.client.post(reverse("add_bank_questions", args=[quiz_two.pk]), {
            "bank_question_id": [bank_question.pk],
        }, secure=True)

        self.assertEqual(quiz_one.questions.count(), 1)
        self.assertEqual(quiz_two.questions.count(), 1)
        self.assertNotEqual(quiz_one.questions.get().pk, quiz_two.questions.get().pk)

    def test_non_owning_teacher_cannot_add_bank_questions_to_the_quiz(self):
        bank_question = self._make_bank_question(status=BankQuestion.Status.APPROVED)
        quiz = Quiz.objects.create(subject=self.subject, teacher=self.teacher, title="Fractions Quiz")
        self.client.force_login(self.other_teacher)

        response = self.client.post(reverse("add_bank_questions", args=[quiz.pk]), {
            "bank_question_id": [bank_question.pk],
        }, secure=True)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(quiz.questions.count(), 0)


class RubricTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="rubric-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            username="other-rubric-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(username="rubric-student", password="test-password")
        self.school = School.objects.create(name="Rubric School", slug="rubric-school")
        SchoolMembership.objects.create(school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(
            school=self.school, user=self.other_teacher, role=SchoolMembership.Role.TEACHER
        )
        SchoolMembership.objects.create(school=self.school, user=self.student, role=SchoolMembership.Role.STUDENT)
        self.subject = Subject.objects.create(school=self.school, name="English")
        Enrollment.objects.create(student=self.student, subject=self.subject)
        self.assignment = Assignment.objects.create(subject=self.subject, teacher=self.teacher, title="Essay")

    def test_teacher_can_add_criteria_via_rubric_page(self):
        self.client.force_login(self.teacher)

        response = self.client.post(reverse("manage_rubric", args=[self.assignment.pk]), {
            "criteria-TOTAL_FORMS": "1", "criteria-INITIAL_FORMS": "0",
            "criteria-MIN_NUM_FORMS": "0", "criteria-MAX_NUM_FORMS": "1000",
            "criteria-0-name": "Clarity", "criteria-0-description": "Is it clear?",
            "criteria-0-max_points": "40", "criteria-0-order": "1",
        }, secure=True)

        self.assertRedirects(
            response, reverse("manage_rubric", args=[self.assignment.pk]), fetch_redirect_response=False
        )
        criterion = RubricCriterion.objects.get(assignment=self.assignment)
        self.assertEqual(criterion.name, "Clarity")
        self.assertEqual(criterion.max_points, 40)

    def test_non_owning_teacher_cannot_manage_rubric(self):
        self.client.force_login(self.other_teacher)

        response = self.client.get(reverse("manage_rubric", args=[self.assignment.pk]), secure=True)

        self.assertEqual(response.status_code, 404)

    def _submit(self):
        upload = SimpleUploadedFile("essay.pdf", b"%PDF-1.4 fake content", content_type="application/pdf")
        return self.client.post(
            reverse("assignment_detail", args=[self.assignment.pk]), {"file": upload}, secure=True
        )

    @patch("quizzes.views.suggest_assignment_grade")
    def test_submitting_with_criteria_creates_criterion_scores_and_sums_ai_score(self, mock_suggest):
        RubricCriterion.objects.create(assignment=self.assignment, name="Clarity", max_points=40, order=1)
        RubricCriterion.objects.create(assignment=self.assignment, name="Grammar", max_points=60, order=2)
        mock_suggest.return_value = {
            "criteria": [
                {"score": 30, "feedback": "Clear enough."}, {"score": 50, "feedback": "Mostly correct."},
            ],
            "overall_feedback": "Good effort overall.",
        }
        self.client.force_login(self.student)

        self._submit()

        submission = AssignmentSubmission.objects.get(assignment=self.assignment)
        self.assertEqual(submission.criterion_scores.count(), 2)
        self.assertEqual(submission.ai_suggested_score, 80)
        self.assertEqual(submission.max_score, 100)
        self.assertEqual(submission.ai_suggested_feedback, "Good effort overall.")

    @patch("quizzes.views.suggest_assignment_grade")
    def test_submitting_with_no_criteria_skips_ai_entirely(self, mock_suggest):
        self.client.force_login(self.student)

        self._submit()

        submission = AssignmentSubmission.objects.get(assignment=self.assignment)
        self.assertIsNone(submission.ai_suggested_score)
        self.assertEqual(submission.ai_suggested_feedback, "")
        self.assertEqual(CriterionScore.objects.count(), 0)
        mock_suggest.assert_not_called()


class QuizTakeCrossQuestionChoiceTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="take-student", password="test-password")
        self.teacher = User.objects.create_user(
            username="take-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.school = School.objects.create(name="Take School", slug="take-school")
        SchoolMembership.objects.create(school=self.school, user=self.student, role=SchoolMembership.Role.STUDENT)
        SchoolMembership.objects.create(school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER)
        self.subject = Subject.objects.create(school=self.school, name="Science")
        Enrollment.objects.create(student=self.student, subject=self.subject)
        self.quiz = Quiz.objects.create(subject=self.subject, teacher=self.teacher, title="Cross Question Quiz")
        self.question_one = Question.objects.create(
            quiz=self.quiz, text="Q1", question_type=Question.QuestionType.MULTIPLE_CHOICE
        )
        self.question_two = Question.objects.create(
            quiz=self.quiz, text="Q2", question_type=Question.QuestionType.MULTIPLE_CHOICE
        )
        Choice.objects.create(question=self.question_one, text="Wrong", is_correct=False)
        self.foreign_correct_choice = Choice.objects.create(
            question=self.question_two, text="Right for Q2", is_correct=True
        )

    def test_submitting_a_choice_id_from_another_question_is_not_counted_correct(self):
        self.client.force_login(self.student)

        self.client.post(reverse("quiz_take", args=[self.quiz.pk]), {
            f"question_{self.question_one.id}": self.foreign_correct_choice.id,
            f"question_{self.question_two.id}": self.foreign_correct_choice.id,
        }, secure=True)

        submission = Submission.objects.get(quiz=self.quiz, student=self.student)
        answer_one = Answer.objects.get(submission=submission, question=self.question_one)
        self.assertFalse(answer_one.is_correct)
        self.assertIsNone(answer_one.selected_choice)

        answer_two = Answer.objects.get(submission=submission, question=self.question_two)
        self.assertTrue(answer_two.is_correct)
        self.assertEqual(answer_two.selected_choice, self.foreign_correct_choice)
