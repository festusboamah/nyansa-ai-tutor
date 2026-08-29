from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academics.models import (
    AcademicYear,
    ClassEnrollment,
    SchoolClass,
    SubjectOffering,
    TeacherAssignment,
    Term,
)
from accounts.models import User
from courses.models import Subject
from schools.models import School, SchoolMembership

from .models import ExamFeeWaiver, ExamIntegrityEvent, ExamSnapshot, Question, Quiz, Submission


def _fake_response(text):
    return Mock(content=[Mock(text=text)], usage=Mock(input_tokens=10, output_tokens=10))


class ExamTestBase(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Exam School", slug="exam-school")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027",
            start_date=date(2026, 9, 1), end_date=date(2027, 7, 31), is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", order=1,
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15),
        )
        self.school_class = SchoolClass.objects.create(
            school=self.school, academic_year=self.year, name="SHS 2 Science"
        )
        self.subject = Subject.objects.create(school=self.school, name="Physics")
        self.offering = SubjectOffering.objects.create(
            school=self.school, school_class=self.school_class, subject=self.subject, term=self.term,
        )

        self.teacher_user = User.objects.create_user(
            username="teacher", password="test-password", role=User.Role.TEACHER
        )
        self.teacher_membership = SchoolMembership.objects.create(
            school=self.school, user=self.teacher_user, role=SchoolMembership.Role.TEACHER
        )
        TeacherAssignment.objects.create(offering=self.offering, teacher=self.teacher_membership, is_lead=True)

        self.student_user = User.objects.create_user(username="student", password="test-password")
        self.student_membership = SchoolMembership.objects.create(
            school=self.school, user=self.student_user, role=SchoolMembership.Role.STUDENT
        )
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.student_membership)

        self.outsider_user = User.objects.create_user(username="outsider", password="test-password")
        SchoolMembership.objects.create(
            school=self.school, user=self.outsider_user, role=SchoolMembership.Role.STUDENT
        )
        # Deliberately not enrolled in school_class - not on this exam's roster.

        self.quiz = Quiz.objects.create(
            subject=self.subject, teacher=self.teacher_user, title="End of Term Physics",
            assessment_type=Quiz.AssessmentType.EXAM, status=Quiz.Status.DRAFT,
            time_limit_minutes=30, max_attempts=1,
        )
        self.quiz.offerings.add(self.offering)
        self.mcq_question = Question.objects.create(
            quiz=self.quiz, text="2+2?", question_type=Question.QuestionType.MULTIPLE_CHOICE, points=1, order=1,
        )
        self.correct_choice = self.mcq_question.choices.create(text="4", is_correct=True)
        self.mcq_question.choices.create(text="5", is_correct=False)

    def _publish(self):
        self.quiz.status = Quiz.Status.PUBLISHED
        self.quiz.save()

    def _start_attempt_as_student(self):
        self.client.force_login(self.student_user)
        self.client.post(reverse("start_exam_attempt", args=[self.quiz.id]), secure=True)
        return Submission.objects.get(quiz=self.quiz, student=self.student_user)


class ExamWindowAndFeeGateTests(ExamTestBase):
    def test_start_exam_attempt_blocked_before_window_opens(self):
        self.quiz.starts_at = timezone.now() + timedelta(hours=1)
        self._publish()
        self.client.force_login(self.student_user)

        response = self.client.post(reverse("start_exam_attempt", args=[self.quiz.id]), secure=True)

        self.assertRedirects(response, reverse("quiz_start", args=[self.quiz.id]), fetch_redirect_response=False)
        self.assertFalse(Submission.objects.filter(quiz=self.quiz, student=self.student_user).exists())

    def test_start_exam_attempt_blocked_after_deadline(self):
        self.quiz.deadline = timezone.now() - timedelta(hours=1)
        self._publish()
        self.client.force_login(self.student_user)

        response = self.client.post(reverse("start_exam_attempt", args=[self.quiz.id]), secure=True)

        self.assertRedirects(response, reverse("quiz_start", args=[self.quiz.id]), fetch_redirect_response=False)
        self.assertFalse(Submission.objects.filter(quiz=self.quiz, student=self.student_user).exists())

    def test_start_exam_attempt_blocked_for_student_not_on_roster(self):
        self._publish()
        self.client.force_login(self.outsider_user)

        response = self.client.post(reverse("start_exam_attempt", args=[self.quiz.id]), secure=True)

        self.assertRedirects(response, reverse("quiz_start", args=[self.quiz.id]), fetch_redirect_response=False)
        self.assertFalse(Submission.objects.filter(quiz=self.quiz, student=self.outsider_user).exists())

    @patch("quizzes.exam_fees.get_fee_balance")
    def test_start_exam_attempt_blocked_by_fee_balance(self, mock_balance):
        mock_balance.return_value = Decimal("50.00")
        self._publish()
        self.client.force_login(self.student_user)

        response = self.client.post(reverse("start_exam_attempt", args=[self.quiz.id]), secure=True)

        self.assertRedirects(response, reverse("quiz_start", args=[self.quiz.id]), fetch_redirect_response=False)
        self.assertFalse(Submission.objects.filter(quiz=self.quiz, student=self.student_user).exists())

    @patch("quizzes.exam_fees.get_fee_balance")
    def test_exam_fee_waiver_unblocks_start(self, mock_balance):
        mock_balance.return_value = Decimal("50.00")
        self._publish()
        ExamFeeWaiver.objects.create(
            student=self.student_membership, quiz=self.quiz, granted_by=self.teacher_membership, reason="Bursary",
        )
        self.client.force_login(self.student_user)

        response = self.client.post(reverse("start_exam_attempt", args=[self.quiz.id]), secure=True)

        submission = Submission.objects.get(quiz=self.quiz, student=self.student_user)
        self.assertRedirects(response, reverse("exam_take", args=[self.quiz.id, submission.id]), fetch_redirect_response=False)


class ExamAttemptTimingTests(ExamTestBase):
    def test_exam_take_view_discards_late_post_past_grace_period(self):
        self._publish()
        submission = Submission.objects.create(
            quiz=self.quiz, student=self.student_user,
            started_at=timezone.now() - timedelta(minutes=40),
            submitted_at=None,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.client.force_login(self.student_user)

        self.client.post(
            reverse("exam_take", args=[self.quiz.id, submission.id]),
            {f"question_{self.mcq_question.id}": self.correct_choice.id},
            secure=True,
        )

        submission.refresh_from_db()
        self.assertIsNotNone(submission.submitted_at)
        answer = submission.answers.get(question=self.mcq_question)
        self.assertIsNone(answer.selected_choice)
        self.assertFalse(answer.is_correct)

    def test_exam_take_view_auto_finalizes_expired_attempt_on_get(self):
        self._publish()
        submission = Submission.objects.create(
            quiz=self.quiz, student=self.student_user,
            started_at=timezone.now() - timedelta(minutes=40),
            submitted_at=None,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("exam_take", args=[self.quiz.id, submission.id]), secure=True)

        submission.refresh_from_db()
        self.assertIsNotNone(submission.submitted_at)
        self.assertRedirects(response, reverse("quiz_result", args=[submission.id]), fetch_redirect_response=False)


class ExamEssayGradingTests(ExamTestBase):
    @patch("ai_core.client.client")
    def test_essay_ai_suggestion_stays_separate_until_teacher_grades(self, mock_client):
        self.quiz.essay_weight_percent = Decimal("50.00")
        self.quiz.save(update_fields=["essay_weight_percent"])
        self._publish()
        essay_question = Question.objects.create(
            quiz=self.quiz, text="Explain Newton's second law.",
            question_type=Question.QuestionType.ESSAY, points=10, order=2,
        )
        mock_client.messages.create.return_value = _fake_response(
            '{"points": 7, "feedback": "Good but incomplete."}'
        )

        submission = self._start_attempt_as_student()
        self.client.post(
            reverse("exam_take", args=[self.quiz.id, submission.id]),
            {
                f"question_{self.mcq_question.id}": self.correct_choice.id,
                f"question_{essay_question.id}": "Force equals mass times acceleration.",
            },
            secure=True,
        )

        submission.refresh_from_db()
        essay_answer = submission.answers.get(question=essay_question)
        self.assertEqual(essay_answer.ai_suggested_points, 7)
        self.assertIsNone(essay_answer.points_awarded)
        self.assertIsNone(submission.score)

        self.client.force_login(self.teacher_user)
        self.client.post(
            reverse("exam_attempt_detail", args=[submission.id]),
            {
                "essay-TOTAL_FORMS": "1", "essay-INITIAL_FORMS": "1",
                "essay-MIN_NUM_FORMS": "0", "essay-MAX_NUM_FORMS": "1000",
                "essay-0-id": str(essay_answer.id),
                "essay-0-points_awarded": "8",
                "essay-0-teacher_feedback": "Well explained.",
            },
            secure=True,
        )

        essay_answer.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(essay_answer.points_awarded, 8)
        # objective 100% * 50 weight + essay 80% * 50 weight = 90
        self.assertEqual(submission.score, 90.0)


class ExamPublishValidationTests(ExamTestBase):
    def test_quiz_clean_rejects_essay_weight_out_of_range(self):
        self.quiz.essay_weight_percent = Decimal("150.00")
        with self.assertRaises(ValidationError):
            self.quiz.clean()

    def test_publish_rejected_when_essay_question_has_zero_weight(self):
        Question.objects.create(
            quiz=self.quiz, text="Essay Q", question_type=Question.QuestionType.ESSAY, points=10, order=2,
        )
        self.client.force_login(self.teacher_user)

        self.client.post(reverse("publish_quiz", args=[self.quiz.id]), secure=True)

        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.status, Quiz.Status.DRAFT)

    def test_publish_succeeds_once_essay_weight_set(self):
        Question.objects.create(
            quiz=self.quiz, text="Essay Q", question_type=Question.QuestionType.ESSAY, points=10, order=2,
        )
        self.quiz.essay_weight_percent = Decimal("40.00")
        self.quiz.save(update_fields=["essay_weight_percent"])
        self.client.force_login(self.teacher_user)

        self.client.post(reverse("publish_quiz", args=[self.quiz.id]), secure=True)

        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.status, Quiz.Status.PUBLISHED)


class ExamResultsReleaseTests(ExamTestBase):
    def _submit_mcq_only(self, submission):
        self.client.post(
            reverse("exam_take", args=[self.quiz.id, submission.id]),
            {f"question_{self.mcq_question.id}": self.correct_choice.id},
            secure=True,
        )

    def test_instant_release_shows_score_immediately(self):
        self._publish()
        submission = self._start_attempt_as_student()
        self._submit_mcq_only(submission)

        response = self.client.get(reverse("quiz_result", args=[submission.id]), secure=True)
        self.assertTrue(response.context["results_visible"])

    def test_manual_release_hides_score_until_published(self):
        self.quiz.results_release_mode = Quiz.ResultsReleaseMode.MANUAL
        self.quiz.save(update_fields=["results_release_mode"])
        self._publish()
        submission = self._start_attempt_as_student()
        self._submit_mcq_only(submission)

        response = self.client.get(reverse("quiz_result", args=[submission.id]), secure=True)
        self.assertFalse(response.context["results_visible"])

        self.client.force_login(self.teacher_user)
        self.client.post(reverse("publish_exam_results", args=[self.quiz.id]), secure=True)

        self.client.force_login(self.student_user)
        response = self.client.get(reverse("quiz_result", args=[submission.id]), secure=True)
        self.assertTrue(response.context["results_visible"])

    def test_scheduled_release_via_management_command(self):
        self.quiz.results_release_mode = Quiz.ResultsReleaseMode.SCHEDULED
        self.quiz.results_release_at = timezone.now() - timedelta(minutes=1)
        self.quiz.save(update_fields=["results_release_mode", "results_release_at"])
        self._publish()
        submission = self._start_attempt_as_student()
        self._submit_mcq_only(submission)

        response = self.client.get(reverse("quiz_result", args=[submission.id]), secure=True)
        self.assertFalse(response.context["results_visible"])

        call_command("release_exam_results")

        response = self.client.get(reverse("quiz_result", args=[submission.id]), secure=True)
        self.assertTrue(response.context["results_visible"])


class ExamAccessControlTests(ExamTestBase):
    def test_student_cannot_access_grading_queue(self):
        self._publish()
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("exam_grading_queue", args=[self.quiz.id]), secure=True)

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_other_teacher_cannot_access_this_exams_grading_queue(self):
        other_teacher = User.objects.create_user(
            username="other-teacher", password="test-password", role=User.Role.TEACHER
        )
        SchoolMembership.objects.create(
            school=self.school, user=other_teacher, role=SchoolMembership.Role.TEACHER
        )
        self.client.force_login(other_teacher)

        response = self.client.get(reverse("exam_grading_queue", args=[self.quiz.id]), secure=True)

        self.assertEqual(response.status_code, 404)


class ExamWebcamConsentTests(ExamTestBase):
    def setUp(self):
        super().setUp()
        self.quiz.require_webcam_snapshots = True
        self.quiz.save(update_fields=["require_webcam_snapshots"])

    def test_start_exam_attempt_redirects_to_consent_when_webcam_required(self):
        self._publish()
        self.client.force_login(self.student_user)

        response = self.client.post(reverse("start_exam_attempt", args=[self.quiz.id]), secure=True)

        self.assertRedirects(
            response, reverse("exam_consent", args=[self.quiz.id]), fetch_redirect_response=False
        )
        self.assertFalse(Submission.objects.filter(quiz=self.quiz, student=self.student_user).exists())

    def test_exam_consent_post_creates_submission_with_consent_flag(self):
        self._publish()
        self.client.force_login(self.student_user)

        response = self.client.post(
            reverse("exam_consent", args=[self.quiz.id]), {"consent": "yes"}, secure=True
        )

        submission = Submission.objects.get(quiz=self.quiz, student=self.student_user)
        self.assertTrue(submission.camera_consent_given)
        self.assertIsNotNone(submission.camera_consent_at)
        self.assertRedirects(
            response, reverse("exam_take", args=[self.quiz.id, submission.id]), fetch_redirect_response=False
        )

    def test_exam_consent_requires_checkbox(self):
        self._publish()
        self.client.force_login(self.student_user)

        response = self.client.post(reverse("exam_consent", args=[self.quiz.id]), {}, secure=True)

        self.assertRedirects(response, reverse("quiz_start", args=[self.quiz.id]), fetch_redirect_response=False)
        self.assertFalse(Submission.objects.filter(quiz=self.quiz, student=self.student_user).exists())

    def test_exam_consent_still_enforces_fee_gate(self):
        self._publish()
        with patch("quizzes.exam_fees.get_fee_balance", return_value=Decimal("50.00")):
            self.client.force_login(self.student_user)
            response = self.client.post(
                reverse("exam_consent", args=[self.quiz.id]), {"consent": "yes"}, secure=True
            )

        self.assertRedirects(response, reverse("quiz_start", args=[self.quiz.id]), fetch_redirect_response=False)
        self.assertFalse(Submission.objects.filter(quiz=self.quiz, student=self.student_user).exists())


class ExamIntegrityLoggingTests(ExamTestBase):
    def setUp(self):
        super().setUp()
        self._publish()
        self.submission = self._start_attempt_as_student()

    def test_integrity_event_logging_flags_submission(self):
        response = self.client.post(
            reverse("exam_integrity_event", args=[self.submission.id]),
            {"event_type": "TAB_HIDDEN", "detail": "left the tab"},
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.submission.refresh_from_db()
        self.assertTrue(self.submission.flagged_for_review)
        event = ExamIntegrityEvent.objects.get(submission=self.submission)
        self.assertEqual(event.event_type, "TAB_HIDDEN")
        self.assertEqual(event.detail, "left the tab")

    def test_integrity_event_rejects_invalid_type(self):
        response = self.client.post(
            reverse("exam_integrity_event", args=[self.submission.id]),
            {"event_type": "NOT_A_REAL_TYPE"},
            secure=True,
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ExamIntegrityEvent.objects.filter(submission=self.submission).exists())

    def test_integrity_event_scoped_to_owning_student(self):
        self.client.force_login(self.outsider_user)

        response = self.client.post(
            reverse("exam_integrity_event", args=[self.submission.id]),
            {"event_type": "BLUR"},
            secure=True,
        )

        self.assertEqual(response.status_code, 404)

    def test_integrity_event_rejected_once_submission_finished(self):
        self.submission.submitted_at = timezone.now()
        self.submission.save(update_fields=["submitted_at"])

        response = self.client.post(
            reverse("exam_integrity_event", args=[self.submission.id]),
            {"event_type": "BLUR"},
            secure=True,
        )

        self.assertEqual(response.status_code, 404)

    def test_snapshot_upload_creates_snapshot(self):
        image = SimpleUploadedFile("snapshot.jpg", b"fake-image-bytes", content_type="image/jpeg")

        response = self.client.post(
            reverse("exam_snapshot_upload", args=[self.submission.id]),
            {"image": image, "trigger": "INTERVAL"},
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        snapshot = ExamSnapshot.objects.get(submission=self.submission)
        self.assertEqual(snapshot.trigger, "INTERVAL")

    def test_snapshot_upload_requires_image(self):
        response = self.client.post(
            reverse("exam_snapshot_upload", args=[self.submission.id]), {"trigger": "INTERVAL"}, secure=True,
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ExamSnapshot.objects.filter(submission=self.submission).exists())


class ExamFlagReviewTests(ExamTestBase):
    def setUp(self):
        super().setUp()
        self._publish()
        self.submission = self._start_attempt_as_student()
        self.client.post(
            reverse("exam_integrity_event", args=[self.submission.id]),
            {"event_type": "BLUR"},
            secure=True,
        )
        self.submission.refresh_from_db()
        self.assertTrue(self.submission.flagged_for_review)

    def test_teacher_can_clear_flag(self):
        self.client.force_login(self.teacher_user)

        self.client.post(reverse("clear_exam_flag", args=[self.submission.id]), secure=True)

        self.submission.refresh_from_db()
        self.assertFalse(self.submission.flagged_for_review)

    def test_student_cannot_clear_own_flag(self):
        response = self.client.post(reverse("clear_exam_flag", args=[self.submission.id]), secure=True)

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.submission.refresh_from_db()
        self.assertTrue(self.submission.flagged_for_review)

    def test_other_teacher_cannot_clear_flag(self):
        other_teacher = User.objects.create_user(
            username="other-teacher-2", password="test-password", role=User.Role.TEACHER
        )
        SchoolMembership.objects.create(
            school=self.school, user=other_teacher, role=SchoolMembership.Role.TEACHER
        )
        self.client.force_login(other_teacher)

        response = self.client.post(reverse("clear_exam_flag", args=[self.submission.id]), secure=True)

        self.assertEqual(response.status_code, 404)
        self.submission.refresh_from_db()
        self.assertTrue(self.submission.flagged_for_review)
