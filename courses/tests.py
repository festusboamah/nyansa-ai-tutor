from unittest.mock import Mock, patch

from django.test import TestCase
from django.db import IntegrityError
from django.urls import reverse

from accounts.models import User
from ai_core.models import AIUsageEvent
from quizzes.models import Assignment, AssignmentSubmission, Quiz, Submission
from schools.models import School, SchoolMembership

from .grading import calculate_subject_grade, letter_grade
from .models import Enrollment, Material, StudyDocument, Subject
from . import study_ai


def _fake_response(text):
    return Mock(content=[Mock(text=text)], usage=Mock(input_tokens=10, output_tokens=20))


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
        self.school = School.objects.create(name="Grade School", slug="grade-school")
        SchoolMembership.objects.create(
            school=self.school, user=self.student, role=SchoolMembership.Role.STUDENT
        )
        SchoolMembership.objects.create(
            school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER
        )
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")

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
        school = School.objects.create(name="Constraint School", slug="constraint-school")
        subject = Subject.objects.create(school=school, name="Constraint Science")
        Enrollment.objects.create(student=student, subject=subject)

        with self.assertRaises(IntegrityError):
            Enrollment.objects.create(student=student, subject=subject)


class CourseAccessBaselineTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="student", password="test-password")
        self.teacher = User.objects.create_user(
            username="teacher", password="test-password", role=User.Role.TEACHER
        )
        self.school = School.objects.create(name="Access School", slug="access-school")
        SchoolMembership.objects.create(
            school=self.school, user=self.student, role=SchoolMembership.Role.STUDENT
        )
        SchoolMembership.objects.create(
            school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER
        )
        self.subject = Subject.objects.create(school=self.school, name="Science")

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

    def test_student_cannot_open_another_schools_subject(self):
        other_school = School.objects.create(name="Other School", slug="other-school")
        other_subject = Subject.objects.create(school=other_school, name="Private Subject")
        self.client.force_login(self.student)

        response = self.client.get(
            reverse("subject_detail", args=[other_subject.id]), secure=True
        )

        self.assertEqual(response.status_code, 404)

    def test_subject_browser_excludes_another_schools_subject(self):
        other_school = School.objects.create(name="Other School", slug="other-school")
        Subject.objects.create(school=other_school, name="Private Subject")
        self.client.force_login(self.student)

        response = self.client.get(reverse("browse_subjects"), secure=True)

        self.assertContains(response, self.subject.name)
        self.assertNotContains(response, "Private Subject")

    def test_global_teacher_role_does_not_override_student_membership(self):
        user = User.objects.create_user(
            username="legacy-teacher",
            password="test-password",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            school=self.school, user=user, role=SchoolMembership.Role.STUDENT
        )
        self.client.force_login(user)

        response = self.client.get(reverse("create_subject"), secure=True)

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_school_admin_membership_can_open_subject_creation(self):
        admin_user = User.objects.create_user(username="school-admin", password="test-password")
        SchoolMembership.objects.create(
            school=self.school,
            user=admin_user,
            role=SchoolMembership.Role.SCHOOL_ADMIN,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("create_subject"), secure=True)

        self.assertEqual(response.status_code, 200)


class StudyAITests(TestCase):
    @patch("ai_core.client.client")
    def test_generate_summary_returns_text_on_success(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("A tidy summary.")
        self.assertEqual(study_ai.generate_summary("some extracted text"), "A tidy summary.")

    @patch("ai_core.client.client")
    def test_generate_summary_falls_back_on_ai_failure(self, mock_client):
        mock_client.messages.create.side_effect = RuntimeError("down")
        result = study_ai.generate_summary("some extracted text")
        self.assertEqual(result, "Summary generation is temporarily unavailable. Please try again later.")

    @patch("ai_core.client.client")
    def test_answer_question_returns_text_on_success(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("The answer is 42.")
        result = study_ai.answer_question_about_document("document text", "What is the answer?")
        self.assertEqual(result, "The answer is 42.")

    @patch("ai_core.client.client")
    def test_answer_question_falls_back_on_ai_failure(self, mock_client):
        mock_client.messages.create.side_effect = RuntimeError("down")
        result = study_ai.answer_question_about_document("document text", "What is the answer?")
        self.assertEqual(result, "Sorry, I couldn't process your question right now. Please try again.")

    @patch("ai_core.client.client")
    def test_generate_summary_logs_usage_event_when_school_given(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("A tidy summary.")
        school = School.objects.create(name="Usage School", slug="study-ai-usage-school")

        study_ai.generate_summary("some extracted text", school=school)

        event = AIUsageEvent.objects.get(school=school)
        self.assertEqual(event.source, AIUsageEvent.Source.STUDY_AI)
        self.assertEqual(event.input_tokens, 10)


class MaterialTextExtractionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Material School", slug="material-school")
        self.teacher = User.objects.create_user(
            username="material-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")

    def test_returns_cached_text_without_re_extracting(self):
        material = Material.objects.create(
            subject=self.subject, teacher=self.teacher, title="Notes",
            material_type=Material.MaterialType.DOCUMENT, file="materials/notes.pdf",
            extracted_text="Already extracted.",
        )
        with patch.object(study_ai, "extract_text_from_pdf") as mock_extract:
            result = study_ai.get_or_extract_material_text(material)
        mock_extract.assert_not_called()
        self.assertEqual(result, "Already extracted.")

    def test_extracts_and_caches_on_first_use(self):
        material = Material.objects.create(
            subject=self.subject, teacher=self.teacher, title="Notes",
            material_type=Material.MaterialType.DOCUMENT, file="materials/notes.pdf",
        )
        with patch.object(study_ai, "extract_text_from_pdf", return_value="Freshly extracted.") as mock_extract:
            result = study_ai.get_or_extract_material_text(material)
        mock_extract.assert_called_once()
        self.assertEqual(result, "Freshly extracted.")
        material.refresh_from_db()
        self.assertEqual(material.extracted_text, "Freshly extracted.")

    def test_returns_empty_string_for_material_with_no_file(self):
        material = Material.objects.create(
            subject=self.subject, teacher=self.teacher, title="Video link",
            material_type=Material.MaterialType.VIDEO, video_url="https://example.com/video",
        )
        self.assertEqual(study_ai.get_or_extract_material_text(material), "")


class MaterialTextViewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Text View School", slug="text-view-school")
        self.teacher = User.objects.create_user(
            username="text-view-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(username="text-view-student", password="test-password")
        SchoolMembership.objects.create(
            school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER
        )
        SchoolMembership.objects.create(
            school=self.school, user=self.student, role=SchoolMembership.Role.STUDENT
        )
        self.subject = Subject.objects.create(school=self.school, name="History")
        self.material = Material.objects.create(
            subject=self.subject, teacher=self.teacher, title="Notes",
            material_type=Material.MaterialType.DOCUMENT, file="materials/notes.pdf",
            extracted_text="Already extracted text.",
        )

    def test_enrolled_student_can_view_extracted_text(self):
        Enrollment.objects.create(student=self.student, subject=self.subject)
        self.client.force_login(self.student)

        response = self.client.get(
            reverse("material_text", args=[self.material.id]), secure=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Already extracted text.")

    def test_unenrolled_student_is_redirected(self):
        self.client.force_login(self.student)

        response = self.client.get(
            reverse("material_text", args=[self.material.id]), secure=True
        )

        self.assertRedirects(response, reverse("browse_subjects"), fetch_redirect_response=False)

    def test_teacher_can_view_extracted_text_without_enrollment(self):
        self.client.force_login(self.teacher)

        response = self.client.get(
            reverse("material_text", args=[self.material.id]), secure=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Already extracted text.")

    def test_extracts_lazily_when_not_yet_cached(self):
        material = Material.objects.create(
            subject=self.subject, teacher=self.teacher, title="Fresh Notes",
            material_type=Material.MaterialType.DOCUMENT, file="materials/fresh.pdf",
        )
        Enrollment.objects.create(student=self.student, subject=self.subject)
        self.client.force_login(self.student)

        with patch.object(study_ai, "extract_text_from_pdf", return_value="Freshly extracted.") as mock_extract:
            response = self.client.get(
                reverse("material_text", args=[material.id]), secure=True
            )

        mock_extract.assert_called_once()
        self.assertContains(response, "Freshly extracted.")


class DraftQuizVisibilityTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="draft-student", password="test-password")
        self.teacher = User.objects.create_user(
            username="draft-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.school = School.objects.create(name="Draft School", slug="draft-school")
        SchoolMembership.objects.create(school=self.school, user=self.student, role=SchoolMembership.Role.STUDENT)
        SchoolMembership.objects.create(school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER)
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")
        Enrollment.objects.create(student=self.student, subject=self.subject)
        self.draft_quiz = Quiz.objects.create(
            subject=self.subject, teacher=self.teacher, title="Draft Quiz", status=Quiz.Status.DRAFT,
        )
        self.published_quiz = Quiz.objects.create(
            subject=self.subject, teacher=self.teacher, title="Published Quiz", status=Quiz.Status.PUBLISHED,
        )

    def test_student_does_not_see_draft_quiz(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("subject_detail", args=[self.subject.id]), secure=True)

        self.assertNotContains(response, "Draft Quiz")
        self.assertContains(response, "Published Quiz")

    def test_teacher_sees_draft_quiz(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("subject_detail", args=[self.subject.id]), secure=True)

        self.assertContains(response, "Draft Quiz")
        self.assertContains(response, "Published Quiz")


class StudentDashboardStudyGoalsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Dashboard School", slug="dashboard-school")
        self.student_user = User.objects.create_user(username="dash-student", password="test-password")
        self.membership = SchoolMembership.objects.create(
            school=self.school, user=self.student_user, role=SchoolMembership.Role.STUDENT
        )
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")
        Enrollment.objects.create(student=self.student_user, subject=self.subject)

    def test_dashboard_shows_no_due_goal_card_when_no_goals(self):
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("dashboard"), secure=True)

        self.assertNotContains(response, "due for revision")

    def test_dashboard_shows_due_goal_count(self):
        from mastery.models import Strand, StudyGoal, Topic

        strand = Strand.objects.create(school=self.school, subject=self.subject, name="Number", order=1)
        topic = Topic.objects.create(strand=strand, name="Fractions", order=1)
        StudyGoal.objects.create(school=self.school, student=self.membership, topic=topic)
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("dashboard"), secure=True)

        self.assertContains(response, "1 topic due for revision.")


class StudyDocumentDetailAccessTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Study Doc School", slug="study-doc-school")
        self.owner = User.objects.create_user(username="doc-owner", password="test-password")
        self.other_student = User.objects.create_user(username="doc-other-student", password="test-password")
        for user in (self.owner, self.other_student):
            SchoolMembership.objects.create(school=self.school, user=user, role=SchoolMembership.Role.STUDENT)
        self.document = StudyDocument.objects.create(
            school=self.school, student=self.owner, title="Notes", file="study_documents/notes.pdf",
        )

    def test_another_student_in_the_same_school_cannot_open_someone_elses_document(self):
        self.client.force_login(self.other_student)

        response = self.client.get(
            reverse("study_document_detail", args=[self.document.id]), secure=True
        )

        self.assertEqual(response.status_code, 404)
