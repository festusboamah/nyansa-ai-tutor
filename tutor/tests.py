from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, Term
from accounts.models import User
from courses.models import Enrollment, Material, StudyDocument, Subject
from gradebook.models import Assessment, AssessmentCategory, GradeEntry, GradeScheme
from mastery.models import Misconception, Strand, Topic
from schools.models import School, SchoolMembership

from . import engine
from .modes import build_system_prompt
from .models import (
    DifficultyLevel, TutorMessage, TutorMessageRole, TutorMode, TutorSession, TutorSettings, TutorUsageEvent,
)


def _fake_response(text="Here is my reply.", input_tokens=12, output_tokens=8):
    return Mock(
        content=[Mock(text=text)],
        usage=Mock(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class TutorTestCase(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Nyansa School", slug="nyansa-school")
        self.other_school = School.objects.create(name="Other School", slug="other-school")

        self.student = self._membership("student", self.school)
        self.other_student = self._membership("other-student", self.school)
        self.outside_student = self._membership("outside-student", self.other_school)

        self.subject = Subject.objects.create(school=self.school, name="Mathematics")

    def _membership(self, username, school):
        user = User.objects.create_user(username=username, password="test-password")
        SchoolMembership.objects.create(school=school, user=user, role=SchoolMembership.Role.STUDENT)
        return user

    def _session(self, student, school=None, mode=TutorMode.TEACH_ME, **kwargs):
        return TutorSession.objects.create(
            school=school or self.school, student=student, mode=mode, **kwargs
        )


class SessionIsolationTests(TutorTestCase):
    def test_student_cannot_view_another_students_session(self):
        session = self._session(self.other_student)
        self.client.force_login(self.student)
        response = self.client.get(reverse("tutor_session_detail", args=[session.id]), secure=True)
        self.assertEqual(response.status_code, 404)

    def test_student_cannot_view_session_from_another_school(self):
        session = self._session(self.outside_student, school=self.other_school)
        self.client.force_login(self.student)
        response = self.client.get(reverse("tutor_session_detail", args=[session.id]), secure=True)
        self.assertEqual(response.status_code, 404)

    def test_student_cannot_post_to_another_students_session(self):
        session = self._session(self.other_student)
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("tutor_session_detail", args=[session.id]),
            {"message": "hi"},
            secure=True,
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(TutorMessage.objects.filter(session=session).exists())


class StartSessionTests(TutorTestCase):
    def test_each_mode_can_be_started(self):
        self.client.force_login(self.student)
        for mode in TutorMode.values:
            with self.subTest(mode=mode):
                response = self.client.post(
                    reverse("tutor_start_session"), {"mode": mode}, secure=True
                )
                session = TutorSession.objects.filter(student=self.student, mode=mode).first()
                self.assertIsNotNone(session)
                self.assertRedirects(
                    response,
                    reverse("tutor_session_detail", args=[session.id]),
                    fetch_redirect_response=False,
                )

    def test_invalid_mode_is_rejected(self):
        self.client.force_login(self.student)
        self.client.post(reverse("tutor_start_session"), {"mode": "NOT_A_MODE"}, secure=True)
        self.assertFalse(TutorSession.objects.filter(student=self.student).exists())

    def test_session_can_be_grounded_in_a_study_document(self):
        document = StudyDocument.objects.create(
            school=self.school, student=self.student, title="Notes",
            file="study_documents/notes.pdf", extracted_text="Photosynthesis is...",
        )
        self.client.force_login(self.student)
        self.client.post(
            reverse("tutor_start_session"),
            {"mode": TutorMode.TEACH_ME, "document_id": document.id},
            secure=True,
        )
        session = TutorSession.objects.get(student=self.student)
        self.assertEqual(session.study_document, document)


class SystemPromptTests(TestCase):
    def test_each_prompted_mode_has_distinct_instructions(self):
        # EXAM_MODE deliberately has no prompt entry - it never reaches build_system_prompt
        # in production, since engine.send_message short-circuits before building one.
        prompted_modes = [mode for mode in TutorMode.values if mode != TutorMode.EXAM_MODE]
        prompts = {mode: build_system_prompt(mode) for mode in prompted_modes}
        self.assertEqual(len(set(prompts.values())), len(prompts))

    def test_exam_mode_has_no_prompt_entry(self):
        with self.assertRaises(KeyError):
            build_system_prompt(TutorMode.EXAM_MODE)

    def test_grounding_text_is_included_when_provided(self):
        prompt = build_system_prompt(TutorMode.TEACH_ME, grounding_text="Photosynthesis is...")
        self.assertIn("Photosynthesis is...", prompt)

    def test_subject_name_is_included_when_provided(self):
        prompt = build_system_prompt(TutorMode.TEACH_ME, subject_name="Biology")
        self.assertIn("Biology", prompt)

    def test_mastery_context_is_included_when_provided(self):
        prompt = build_system_prompt(TutorMode.REVISE_WITH_ME, mastery_context=["Fractions"])
        self.assertIn("Fractions", prompt)
        self.assertIn("need", prompt.lower())

    def test_hint_guidance_is_included_when_provided(self):
        prompt = build_system_prompt(TutorMode.HINT, hint_guidance="This is hint 2 of 4.")
        self.assertIn("This is hint 2 of 4.", prompt)

    def test_difficulty_range_is_included_when_provided(self):
        prompt = build_system_prompt(TutorMode.PRACTICE, difficulty_range="Keep it Easy to Medium.")
        self.assertIn("Keep it Easy to Medium.", prompt)


class SendMessageEngineTests(TutorTestCase):
    @patch("tutor.engine.client")
    def test_successful_reply_is_persisted_with_usage_event(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("The mitochondria is...")
        session = self._session(self.student, subject=self.subject)

        reply = engine.send_message(session, "What is a mitochondria?")

        self.assertEqual(reply.role, TutorMessageRole.TUTOR)
        self.assertEqual(reply.content, "The mitochondria is...")
        self.assertEqual(session.messages.count(), 2)
        self.assertEqual(session.messages.first().role, TutorMessageRole.STUDENT)

        usage_event = TutorUsageEvent.objects.get(session=session)
        self.assertTrue(usage_event.succeeded)
        self.assertEqual(usage_event.input_tokens, 12)
        self.assertEqual(usage_event.output_tokens, 8)

    @patch("tutor.engine.client")
    def test_grounding_document_text_reaches_the_system_prompt(self, mock_client):
        mock_client.messages.create.return_value = _fake_response()
        document = StudyDocument.objects.create(
            school=self.school, student=self.student, title="Notes",
            file="study_documents/notes.pdf", extracted_text="Photosynthesis is...",
        )
        session = self._session(self.student, study_document=document)

        engine.send_message(session, "Explain this")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("Photosynthesis is...", call_kwargs["system"])

    @patch("tutor.engine.client")
    def test_conversation_history_is_sent_as_multi_turn_messages(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("second reply")
        session = self._session(self.student)
        engine.send_message(session, "first question")
        mock_client.messages.create.return_value = _fake_response("second reply")
        engine.send_message(session, "follow-up question")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        roles = [m["role"] for m in call_kwargs["messages"]]
        self.assertEqual(roles, ["user", "assistant", "user"])

    @patch("tutor.engine.client")
    def test_api_failure_falls_back_gracefully_without_raising(self, mock_client):
        mock_client.messages.create.side_effect = RuntimeError("upstream is down")
        session = self._session(self.student)

        reply = engine.send_message(session, "hello")

        self.assertEqual(reply.content, engine.FALLBACK_REPLY)
        usage_event = TutorUsageEvent.objects.get(session=session)
        self.assertFalse(usage_event.succeeded)
        self.assertIn("upstream is down", usage_event.error_message)


class SessionDetailViewTests(TutorTestCase):
    @patch("tutor.engine.client")
    def test_posting_a_message_persists_conversation_and_redirects(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("Sure, let's break it down.")
        session = self._session(self.student)
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("tutor_session_detail", args=[session.id]),
            {"message": "Can you help me with fractions?"},
            secure=True,
        )

        self.assertRedirects(
            response, reverse("tutor_session_detail", args=[session.id]), fetch_redirect_response=False
        )
        self.assertEqual(session.messages.count(), 2)


class ExamModeEngineTests(TutorTestCase):
    @patch("tutor.engine.client")
    def test_exam_mode_never_calls_claude_and_returns_fixed_reply(self, mock_client):
        session = self._session(self.student, mode=TutorMode.EXAM_MODE)

        reply = engine.send_message(session, "Can you help me with this exam question?")

        mock_client.messages.create.assert_not_called()
        self.assertEqual(reply.content, engine.EXAM_MODE_REPLY)
        self.assertFalse(TutorUsageEvent.objects.filter(session=session).exists())


class RevideWithMeMasteryContextTests(TutorTestCase):
    def setUp(self):
        super().setUp()
        self.membership = SchoolMembership.objects.get(school=self.school, user=self.student)
        year = AcademicYear.objects.create(
            school=self.school, name="2026/2027", start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31), is_current=True,
        )
        term = Term.objects.create(
            academic_year=year, name="Term 1", order=1,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
        )
        school_class = SchoolClass.objects.create(school=self.school, academic_year=year, name="Basic 6")
        ClassEnrollment.objects.create(school_class=school_class, student=self.membership)
        offering = SubjectOffering.objects.create(
            school=self.school, school_class=school_class, subject=self.subject, term=term
        )
        strand = Strand.objects.create(school=self.school, subject=self.subject, name="Number", order=1)
        self.topic = Topic.objects.create(strand=strand, name="Fractions", order=1)
        scheme = GradeScheme.objects.create(
            school=self.school, academic_year=year, name="Standard", status=GradeScheme.Status.ACTIVE
        )
        category = AssessmentCategory.objects.create(
            scheme=scheme, name="Coursework", code="coursework", weight=Decimal("100"), order=1
        )
        assessment = Assessment.objects.create(
            school=self.school, offering=offering, category=category, topic=self.topic,
            title="Fractions quiz", max_score=Decimal("100"), status=Assessment.Status.CLOSED,
        )
        GradeEntry.objects.create(
            school=self.school, assessment=assessment, student=self.membership,
            recorded_by=self.membership, score=Decimal("20"), status=GradeEntry.Status.PUBLISHED,
            review_status=GradeEntry.ReviewStatus.APPROVED, reviewed_by=self.membership,
        )

    @patch("tutor.engine.client")
    def test_revise_with_me_includes_needs_support_topic_in_system_prompt(self, mock_client):
        mock_client.messages.create.return_value = _fake_response()
        session = self._session(self.student, mode=TutorMode.REVISE_WITH_ME, subject=self.subject)

        engine.send_message(session, "Help me revise")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("Fractions", call_kwargs["system"])

    @patch("tutor.engine.client")
    def test_other_modes_do_not_include_mastery_context(self, mock_client):
        mock_client.messages.create.return_value = _fake_response()
        session = self._session(self.student, mode=TutorMode.TEACH_ME, subject=self.subject)

        engine.send_message(session, "Teach me fractions")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertNotIn("recorded mastery evidence", call_kwargs["system"])


class TutorSettingsViewTests(TutorTestCase):
    def _admin(self, username="tutor-admin"):
        user = User.objects.create_user(username=username, password="test-password")
        SchoolMembership.objects.create(school=self.school, user=user, role=SchoolMembership.Role.SCHOOL_ADMIN)
        return user

    def test_non_admin_cannot_access_settings(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("tutor_settings"), secure=True)
        self.assertEqual(response.status_code, 403)

    def test_admin_can_disable_a_mode(self):
        admin = self._admin()
        self.client.force_login(admin)

        response = self.client.post(reverse("tutor_settings"), {
            f"enabled_{value}": "on" for value, _ in TutorMode.choices if value != TutorMode.PRACTICE
        }, secure=True)

        self.assertRedirects(response, reverse("tutor_settings"), fetch_redirect_response=False)
        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertEqual(settings_row.disabled_modes, [TutorMode.PRACTICE])

    def test_disabled_mode_is_hidden_and_cannot_be_started(self):
        TutorSettings.objects.create(school=self.school, disabled_modes=[TutorMode.PRACTICE])
        self.client.force_login(self.student)

        home_response = self.client.get(reverse("tutor_home"), secure=True)
        self.assertNotContains(home_response, "Practice With Me")

        self.client.post(reverse("tutor_start_session"), {"mode": TutorMode.PRACTICE}, secure=True)
        self.assertFalse(TutorSession.objects.filter(student=self.student, mode=TutorMode.PRACTICE).exists())

    def test_admin_can_update_hint_depth_and_reveal_policy(self):
        admin = self._admin()
        self.client.force_login(admin)

        response = self.client.post(reverse("tutor_settings"), {
            "max_hint_depth": "2", "allow_final_answer_reveal": "on",
        }, secure=True)

        self.assertRedirects(response, reverse("tutor_settings"), fetch_redirect_response=False)
        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertEqual(settings_row.max_hint_depth, 2)
        self.assertTrue(settings_row.allow_final_answer_reveal)

    def test_invalid_hint_depth_is_rejected_without_losing_other_settings(self):
        admin = self._admin()
        self.client.force_login(admin)

        self.client.post(reverse("tutor_settings"), {"max_hint_depth": "not-a-number"}, secure=True)

        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertEqual(settings_row.max_hint_depth, 4)

    def test_blank_hint_depth_keeps_current_value(self):
        TutorSettings.objects.create(school=self.school, max_hint_depth=3)
        admin = self._admin()
        self.client.force_login(admin)

        self.client.post(reverse("tutor_settings"), {
            f"enabled_{value}": "on" for value, _ in TutorMode.choices
        }, secure=True)

        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertEqual(settings_row.max_hint_depth, 3)


class HintDepthEngineTests(TutorTestCase):
    @patch("tutor.engine.client")
    def test_early_hints_include_numbered_guidance_and_call_claude(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("Here's a hint.")
        session = self._session(self.student, mode=TutorMode.HINT)

        engine.send_message(session, "I'm stuck on this fraction problem")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("hint 1 of 4", call_kwargs["system"])

    @patch("tutor.engine.client")
    def test_hint_limit_reached_without_reveal_short_circuits(self, mock_client):
        TutorSettings.objects.create(school=self.school, max_hint_depth=2, allow_final_answer_reveal=False)
        mock_client.messages.create.return_value = _fake_response("Here's a hint.")
        session = self._session(self.student, mode=TutorMode.HINT)

        engine.send_message(session, "hint please")  # hint 1
        mock_client.messages.create.return_value = _fake_response("Here's another hint.")
        engine.send_message(session, "another hint please")  # hint 2
        mock_client.messages.create.reset_mock()
        reply = engine.send_message(session, "one more hint please")  # would be hint 3, over the limit

        mock_client.messages.create.assert_not_called()
        self.assertEqual(reply.content, engine.HINT_LIMIT_REPLY)

    @patch("tutor.engine.client")
    def test_hint_limit_reached_with_reveal_allowed_calls_claude_with_reveal_guidance(self, mock_client):
        TutorSettings.objects.create(school=self.school, max_hint_depth=1, allow_final_answer_reveal=True)
        mock_client.messages.create.return_value = _fake_response("Here's a hint.")
        session = self._session(self.student, mode=TutorMode.HINT)

        engine.send_message(session, "hint please")  # hint 1, within limit
        mock_client.messages.create.return_value = _fake_response("The answer is 3/4.")
        engine.send_message(session, "still stuck")  # over the limit, reveal allowed

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("Reveal the final answer", call_kwargs["system"])

    @patch("tutor.engine.client")
    def test_non_hint_modes_are_unaffected_by_hint_settings(self, mock_client):
        TutorSettings.objects.create(school=self.school, max_hint_depth=1, allow_final_answer_reveal=False)
        mock_client.messages.create.return_value = _fake_response("Let's work through it.")
        session = self._session(self.student, mode=TutorMode.GUIDE_ME)

        engine.send_message(session, "question one")
        mock_client.messages.create.return_value = _fake_response("Let's continue.")
        engine.send_message(session, "question two")
        mock_client.messages.create.reset_mock()
        mock_client.messages.create.return_value = _fake_response("Let's continue further.")
        reply = engine.send_message(session, "question three")

        mock_client.messages.create.assert_called_once()
        self.assertNotEqual(reply.content, engine.HINT_LIMIT_REPLY)


class MaterialAndTopicFocusTests(TutorTestCase):
    def setUp(self):
        super().setUp()
        Enrollment.objects.create(student=self.student, subject=self.subject)
        self.teacher_user = User.objects.create_user(username="material-teacher", password="test-password")
        self.material = Material.objects.create(
            subject=self.subject, teacher=self.teacher_user, title="Fractions Notes",
            material_type=Material.MaterialType.DOCUMENT, file="materials/notes.pdf",
            extracted_text="Fractions are parts of a whole.",
        )
        self.strand = Strand.objects.create(school=self.school, subject=self.subject, name="Number", order=1)
        self.topic = Topic.objects.create(strand=self.strand, name="Fractions", order=1)

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_school_id"] = self.school.pk
        session.save()

    def test_start_session_sets_material_and_topic(self):
        self._login(self.student)
        self.client.post(reverse("tutor_start_session"), {
            "mode": TutorMode.HINT, "material_id": self.material.pk, "topic_id": self.topic.pk,
        }, secure=True)

        session = TutorSession.objects.get(student=self.student)
        self.assertEqual(session.material, self.material)
        self.assertEqual(session.topic, self.topic)

    def test_material_from_unenrolled_subject_is_rejected(self):
        other_subject = Subject.objects.create(school=self.school, name="Physics")
        unenrolled_material = Material.objects.create(
            subject=other_subject, teacher=self.teacher_user, title="Physics Notes",
            material_type=Material.MaterialType.DOCUMENT, file="materials/physics.pdf",
        )
        self._login(self.student)
        response = self.client.post(reverse("tutor_start_session"), {
            "mode": TutorMode.HINT, "material_id": unenrolled_material.pk,
        }, secure=True)
        self.assertEqual(response.status_code, 404)

    @patch("tutor.engine.client")
    def test_material_grounding_reaches_system_prompt(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("Here's help.")
        session = self._session(self.student, mode=TutorMode.TEACH_ME, material=self.material)

        engine.send_message(session, "Explain fractions")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("Fractions are parts of a whole.", call_kwargs["system"])

    @patch("tutor.engine.client")
    def test_material_takes_precedence_over_study_document(self, mock_client):
        document = StudyDocument.objects.create(
            school=self.school, student=self.student, title="My Notes",
            file="study_documents/notes.pdf", extracted_text="My own notes content.",
        )
        mock_client.messages.create.return_value = _fake_response("Here's help.")
        session = self._session(
            self.student, mode=TutorMode.TEACH_ME, material=self.material, study_document=document
        )

        engine.send_message(session, "Explain fractions")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("Fractions are parts of a whole.", call_kwargs["system"])
        self.assertNotIn("My own notes content.", call_kwargs["system"])

    @patch("tutor.engine.client")
    def test_topic_focus_reaches_system_prompt(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("Let's focus on fractions.")
        session = self._session(self.student, mode=TutorMode.TEACH_ME, topic=self.topic)

        engine.send_message(session, "Help me study")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("Number · Fractions", call_kwargs["system"])

    @patch("tutor.engine.client")
    def test_material_extraction_is_cached_across_messages_in_session(self, mock_client):
        uncached_material = Material.objects.create(
            subject=self.subject, teacher=self.teacher_user, title="Lazy Notes",
            material_type=Material.MaterialType.DOCUMENT, file="materials/lazy.pdf",
        )
        mock_client.messages.create.return_value = _fake_response("Here's help.")
        session = self._session(self.student, mode=TutorMode.TEACH_ME, material=uncached_material)

        with patch("courses.study_ai.extract_text_from_pdf", return_value="Extracted once.") as mock_extract:
            engine.send_message(session, "first question")
            mock_client.messages.create.return_value = _fake_response("More help.")
            engine.send_message(session, "second question")

        mock_extract.assert_called_once()


class UsageQuotaEngineTests(TutorTestCase):
    @patch("tutor.engine.client")
    def test_no_settings_row_means_unlimited(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("Sure, here's help.")
        session = self._session(self.student, mode=TutorMode.TEACH_ME)

        reply = engine.send_message(session, "question")

        mock_client.messages.create.assert_called_once()
        self.assertNotEqual(reply.content, engine.QUOTA_EXCEEDED_REPLY)

    @patch("tutor.engine.client")
    def test_calls_under_the_limit_go_through(self, mock_client):
        TutorSettings.objects.create(school=self.school, daily_usage_limit=2)
        mock_client.messages.create.return_value = _fake_response("Reply one.")
        session = self._session(self.student, mode=TutorMode.TEACH_ME)

        engine.send_message(session, "first question")

        self.assertEqual(TutorUsageEvent.objects.filter(session__school=self.school).count(), 1)

    @patch("tutor.engine.client")
    def test_call_at_the_limit_short_circuits_without_calling_claude(self, mock_client):
        TutorSettings.objects.create(school=self.school, daily_usage_limit=1)
        mock_client.messages.create.return_value = _fake_response("Reply one.")
        session = self._session(self.student, mode=TutorMode.TEACH_ME)
        engine.send_message(session, "first question")  # uses up the quota

        mock_client.messages.create.reset_mock()
        reply = engine.send_message(session, "second question")

        mock_client.messages.create.assert_not_called()
        self.assertEqual(reply.content, engine.QUOTA_EXCEEDED_REPLY)
        self.assertEqual(TutorUsageEvent.objects.filter(session__school=self.school).count(), 1)

    @patch("tutor.engine.client")
    def test_quota_is_shared_school_wide_across_sessions_and_students(self, mock_client):
        TutorSettings.objects.create(school=self.school, daily_usage_limit=1)
        mock_client.messages.create.return_value = _fake_response("Reply for student one.")
        first_session = self._session(self.student, mode=TutorMode.TEACH_ME)
        engine.send_message(first_session, "question from student one")  # uses up the school's quota

        mock_client.messages.create.reset_mock()
        second_session = self._session(self.other_student, mode=TutorMode.TEACH_ME)
        reply = engine.send_message(second_session, "question from student two")

        mock_client.messages.create.assert_not_called()
        self.assertEqual(reply.content, engine.QUOTA_EXCEEDED_REPLY)

    @patch("tutor.engine.client")
    def test_quota_does_not_apply_to_a_different_school(self, mock_client):
        TutorSettings.objects.create(school=self.school, daily_usage_limit=1)
        mock_client.messages.create.return_value = _fake_response("Reply one.")
        session = self._session(self.student, mode=TutorMode.TEACH_ME)
        engine.send_message(session, "first question")  # uses up self.school's quota

        mock_client.messages.create.reset_mock()
        mock_client.messages.create.return_value = _fake_response("Reply for the other school.")
        other_session = self._session(self.outside_student, school=self.other_school, mode=TutorMode.TEACH_ME)
        reply = engine.send_message(other_session, "question from another school")

        mock_client.messages.create.assert_called_once()
        self.assertNotEqual(reply.content, engine.QUOTA_EXCEEDED_REPLY)


class UsageLimitSettingsViewTests(TutorTestCase):
    def _admin(self, username="quota-admin"):
        user = User.objects.create_user(username=username, password="test-password")
        SchoolMembership.objects.create(school=self.school, user=user, role=SchoolMembership.Role.SCHOOL_ADMIN)
        return user

    def test_admin_can_set_daily_usage_limit(self):
        admin = self._admin()
        self.client.force_login(admin)

        self.client.post(reverse("tutor_settings"), {"daily_usage_limit": "50"}, secure=True)

        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertEqual(settings_row.daily_usage_limit, 50)

    def test_admin_can_clear_daily_usage_limit(self):
        TutorSettings.objects.create(school=self.school, daily_usage_limit=50)
        admin = self._admin()
        self.client.force_login(admin)

        self.client.post(reverse("tutor_settings"), {"daily_usage_limit": ""}, secure=True)

        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertIsNone(settings_row.daily_usage_limit)

    def test_omitting_the_field_leaves_current_limit_untouched(self):
        TutorSettings.objects.create(school=self.school, daily_usage_limit=50)
        admin = self._admin()
        self.client.force_login(admin)

        self.client.post(reverse("tutor_settings"), {
            f"enabled_{value}": "on" for value, _ in TutorMode.choices
        }, secure=True)

        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertEqual(settings_row.daily_usage_limit, 50)


class DifficultyRangeEngineTests(TutorTestCase):
    @patch("tutor.engine.client")
    def test_no_settings_row_sends_no_difficulty_guidance(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("Here's a question.")
        session = self._session(self.student, mode=TutorMode.PRACTICE)

        engine.send_message(session, "give me a practice question")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertNotIn("difficulty range", call_kwargs["system"])

    @patch("tutor.engine.client")
    def test_full_range_settings_send_no_difficulty_guidance(self, mock_client):
        TutorSettings.objects.create(
            school=self.school, min_difficulty=DifficultyLevel.EASY, max_difficulty=DifficultyLevel.HARD,
        )
        mock_client.messages.create.return_value = _fake_response("Here's a question.")
        session = self._session(self.student, mode=TutorMode.PRACTICE)

        engine.send_message(session, "give me a practice question")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertNotIn("difficulty range", call_kwargs["system"])

    @patch("tutor.engine.client")
    def test_narrowed_range_sends_bounded_guidance(self, mock_client):
        TutorSettings.objects.create(
            school=self.school, min_difficulty=DifficultyLevel.EASY, max_difficulty=DifficultyLevel.MEDIUM,
        )
        mock_client.messages.create.return_value = _fake_response("Here's a question.")
        session = self._session(self.student, mode=TutorMode.PRACTICE)

        engine.send_message(session, "give me a practice question")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("difficulty range: Easy to Medium", call_kwargs["system"])

    @patch("tutor.engine.client")
    def test_difficulty_guidance_not_included_for_non_practice_modes(self, mock_client):
        TutorSettings.objects.create(
            school=self.school, min_difficulty=DifficultyLevel.EASY, max_difficulty=DifficultyLevel.MEDIUM,
        )
        mock_client.messages.create.return_value = _fake_response("Let's work through it.")
        session = self._session(self.student, mode=TutorMode.TEACH_ME)

        engine.send_message(session, "explain fractions")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertNotIn("difficulty range", call_kwargs["system"])


class AdaptivePracticeDifficultyEngineTests(TutorTestCase):
    def setUp(self):
        super().setUp()
        self.membership = SchoolMembership.objects.get(school=self.school, user=self.student)
        year = AcademicYear.objects.create(
            school=self.school, name="2026/2027", start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31), is_current=True,
        )
        term = Term.objects.create(
            academic_year=year, name="Term 1", order=1,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
        )
        school_class = SchoolClass.objects.create(school=self.school, academic_year=year, name="Basic 6")
        ClassEnrollment.objects.create(school_class=school_class, student=self.membership)
        offering = SubjectOffering.objects.create(
            school=self.school, school_class=school_class, subject=self.subject, term=term
        )
        strand = Strand.objects.create(school=self.school, subject=self.subject, name="Number", order=1)
        self.topic = Topic.objects.create(strand=strand, name="Fractions", order=1)
        scheme = GradeScheme.objects.create(
            school=self.school, academic_year=year, name="Standard", status=GradeScheme.Status.ACTIVE
        )
        category = AssessmentCategory.objects.create(
            scheme=scheme, name="Coursework", code="coursework", weight=Decimal("100"), order=1
        )
        self.assessment = Assessment.objects.create(
            school=self.school, offering=offering, category=category, topic=self.topic,
            title="Fractions quiz", max_score=Decimal("100"), status=Assessment.Status.CLOSED,
        )

    def _grade(self, score):
        GradeEntry.objects.create(
            school=self.school, assessment=self.assessment, student=self.membership,
            recorded_by=self.membership, score=Decimal(score), status=GradeEntry.Status.PUBLISHED,
            review_status=GradeEntry.ReviewStatus.APPROVED, reviewed_by=self.membership,
        )

    @patch("tutor.engine.client")
    def test_needs_support_student_gets_easy_difficulty_guidance(self, mock_client):
        self._grade("20")
        mock_client.messages.create.return_value = _fake_response("Here's an easy question.")
        session = self._session(self.student, mode=TutorMode.PRACTICE, subject=self.subject, topic=self.topic)

        engine.send_message(session, "give me a practice question")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("at Easy difficulty", call_kwargs["system"])

    @patch("tutor.engine.client")
    def test_mastered_student_gets_hard_difficulty_guidance(self, mock_client):
        self._grade("90")
        mock_client.messages.create.return_value = _fake_response("Here's a hard question.")
        session = self._session(self.student, mode=TutorMode.PRACTICE, subject=self.subject, topic=self.topic)

        engine.send_message(session, "give me a practice question")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("at Hard difficulty", call_kwargs["system"])

    @patch("tutor.engine.client")
    def test_mastered_student_target_clamps_to_school_max(self, mock_client):
        TutorSettings.objects.create(
            school=self.school, min_difficulty=DifficultyLevel.EASY, max_difficulty=DifficultyLevel.MEDIUM,
        )
        self._grade("90")
        mock_client.messages.create.return_value = _fake_response("Here's a medium question.")
        session = self._session(self.student, mode=TutorMode.PRACTICE, subject=self.subject, topic=self.topic)

        engine.send_message(session, "give me a practice question")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn("at Medium difficulty", call_kwargs["system"])
        self.assertNotIn("at Hard difficulty", call_kwargs["system"])

    @patch("tutor.engine.client")
    def test_no_evidence_falls_back_to_static_range_guidance(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("Here's a question.")
        session = self._session(self.student, mode=TutorMode.PRACTICE, subject=self.subject, topic=self.topic)

        engine.send_message(session, "give me a practice question")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertNotIn("current mastery", call_kwargs["system"])
        self.assertNotIn("difficulty range", call_kwargs["system"])


class DifficultyRangeSettingsViewTests(TutorTestCase):
    def _admin(self, username="difficulty-admin"):
        user = User.objects.create_user(username=username, password="test-password")
        SchoolMembership.objects.create(school=self.school, user=user, role=SchoolMembership.Role.SCHOOL_ADMIN)
        return user

    def test_admin_can_save_a_valid_range(self):
        admin = self._admin()
        self.client.force_login(admin)

        self.client.post(reverse("tutor_settings"), {
            "min_difficulty": DifficultyLevel.EASY, "max_difficulty": DifficultyLevel.MEDIUM,
        }, secure=True)

        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertEqual(settings_row.min_difficulty, DifficultyLevel.EASY)
        self.assertEqual(settings_row.max_difficulty, DifficultyLevel.MEDIUM)

    def test_inverted_range_is_rejected(self):
        admin = self._admin()
        self.client.force_login(admin)

        self.client.post(reverse("tutor_settings"), {
            "min_difficulty": DifficultyLevel.HARD, "max_difficulty": DifficultyLevel.EASY,
        }, secure=True)

        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertEqual(settings_row.min_difficulty, DifficultyLevel.EASY)
        self.assertEqual(settings_row.max_difficulty, DifficultyLevel.HARD)


class AssessmentPeriodEngineTests(TutorTestCase):
    @patch("tutor.engine.client")
    def test_no_dates_set_means_available(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("Sure, here's help.")
        session = self._session(self.student, mode=TutorMode.TEACH_ME)

        reply = engine.send_message(session, "question")

        mock_client.messages.create.assert_called_once()
        self.assertNotEqual(reply.content, engine.ASSESSMENT_PERIOD_REPLY)

    @patch("tutor.engine.client")
    def test_today_inside_the_range_short_circuits(self, mock_client):
        today = date.today()
        TutorSettings.objects.create(
            school=self.school,
            restricted_period_start=today - timedelta(days=1),
            restricted_period_end=today + timedelta(days=1),
        )
        session = self._session(self.student, mode=TutorMode.TEACH_ME)

        reply = engine.send_message(session, "question")

        mock_client.messages.create.assert_not_called()
        self.assertEqual(reply.content, engine.ASSESSMENT_PERIOD_REPLY)

    @patch("tutor.engine.client")
    def test_restriction_is_checked_before_exam_mode_and_hint_logic(self, mock_client):
        today = date.today()
        TutorSettings.objects.create(
            school=self.school,
            restricted_period_start=today - timedelta(days=1),
            restricted_period_end=today + timedelta(days=1),
            max_hint_depth=1,
        )
        session = self._session(self.student, mode=TutorMode.EXAM_MODE)

        reply = engine.send_message(session, "question")

        mock_client.messages.create.assert_not_called()
        self.assertEqual(reply.content, engine.ASSESSMENT_PERIOD_REPLY)
        self.assertNotEqual(reply.content, engine.EXAM_MODE_REPLY)

    @patch("tutor.engine.client")
    def test_today_outside_the_range_behaves_normally(self, mock_client):
        today = date.today()
        TutorSettings.objects.create(
            school=self.school,
            restricted_period_start=today + timedelta(days=10),
            restricted_period_end=today + timedelta(days=20),
        )
        mock_client.messages.create.return_value = _fake_response("Sure, here's help.")
        session = self._session(self.student, mode=TutorMode.TEACH_ME)

        reply = engine.send_message(session, "question")

        mock_client.messages.create.assert_called_once()
        self.assertNotEqual(reply.content, engine.ASSESSMENT_PERIOD_REPLY)


class AssessmentPeriodSettingsViewTests(TutorTestCase):
    def _admin(self, username="period-admin"):
        user = User.objects.create_user(username=username, password="test-password")
        SchoolMembership.objects.create(school=self.school, user=user, role=SchoolMembership.Role.SCHOOL_ADMIN)
        return user

    def test_admin_can_set_a_valid_range(self):
        admin = self._admin()
        self.client.force_login(admin)
        today = date.today()

        self.client.post(reverse("tutor_settings"), {
            "restricted_period_start": str(today),
            "restricted_period_end": str(today + timedelta(days=5)),
        }, secure=True)

        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertEqual(settings_row.restricted_period_start, today)
        self.assertEqual(settings_row.restricted_period_end, today + timedelta(days=5))

    def test_admin_can_clear_the_range(self):
        today = date.today()
        TutorSettings.objects.create(
            school=self.school, restricted_period_start=today, restricted_period_end=today + timedelta(days=5),
        )
        admin = self._admin()
        self.client.force_login(admin)

        self.client.post(reverse("tutor_settings"), {
            "restricted_period_start": "", "restricted_period_end": "",
        }, secure=True)

        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertIsNone(settings_row.restricted_period_start)
        self.assertIsNone(settings_row.restricted_period_end)

    def test_inverted_range_is_rejected(self):
        admin = self._admin()
        self.client.force_login(admin)
        today = date.today()

        self.client.post(reverse("tutor_settings"), {
            "restricted_period_start": str(today + timedelta(days=5)),
            "restricted_period_end": str(today),
        }, secure=True)

        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertIsNone(settings_row.restricted_period_start)
        self.assertIsNone(settings_row.restricted_period_end)

    def test_partial_range_is_rejected(self):
        admin = self._admin()
        self.client.force_login(admin)
        today = date.today()

        self.client.post(reverse("tutor_settings"), {
            "restricted_period_start": str(today),
        }, secure=True)

        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertIsNone(settings_row.restricted_period_start)
        self.assertIsNone(settings_row.restricted_period_end)

    def test_omitting_both_fields_leaves_current_range_untouched(self):
        today = date.today()
        TutorSettings.objects.create(
            school=self.school, restricted_period_start=today, restricted_period_end=today + timedelta(days=5),
        )
        admin = self._admin()
        self.client.force_login(admin)

        self.client.post(reverse("tutor_settings"), {
            f"enabled_{value}": "on" for value, _ in TutorMode.choices
        }, secure=True)

        settings_row = TutorSettings.objects.get(school=self.school)
        self.assertEqual(settings_row.restricted_period_start, today)
        self.assertEqual(settings_row.restricted_period_end, today + timedelta(days=5))


class MisconceptionTrackingEngineTests(TutorTestCase):
    @patch("tutor.engine.client")
    def test_successful_explain_my_mistake_reply_creates_misconception(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("You likely confused numerator and denominator.")
        session = self._session(self.student, mode=TutorMode.EXPLAIN_MY_MISTAKE)

        engine.send_message(session, "I said 2/4 + 1/4 = 3/8 but the answer is 3/4")

        misconception = Misconception.objects.get(source_session=session)
        self.assertEqual(misconception.student_description, "I said 2/4 + 1/4 = 3/8 but the answer is 3/4")
        self.assertEqual(misconception.hypothesis, "You likely confused numerator and denominator.")
        self.assertEqual(misconception.status, Misconception.Status.OPEN)

    @patch("tutor.engine.client")
    def test_second_message_in_same_session_updates_not_duplicates(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("First hypothesis.")
        session = self._session(self.student, mode=TutorMode.EXPLAIN_MY_MISTAKE)
        engine.send_message(session, "first description")

        mock_client.messages.create.return_value = _fake_response("Refined hypothesis.")
        engine.send_message(session, "clarified description")

        self.assertEqual(Misconception.objects.filter(source_session=session).count(), 1)
        misconception = Misconception.objects.get(source_session=session)
        self.assertEqual(misconception.hypothesis, "Refined hypothesis.")
        self.assertEqual(misconception.student_description, "clarified description")

    @patch("tutor.engine.client")
    def test_failed_ai_call_creates_no_misconception(self, mock_client):
        mock_client.messages.create.side_effect = RuntimeError("down")
        session = self._session(self.student, mode=TutorMode.EXPLAIN_MY_MISTAKE)

        engine.send_message(session, "description")

        self.assertFalse(Misconception.objects.filter(source_session=session).exists())

    @patch("tutor.engine.client")
    def test_other_modes_do_not_create_misconceptions(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("Sure, here's an explanation.")
        session = self._session(self.student, mode=TutorMode.TEACH_ME)

        engine.send_message(session, "explain fractions")

        self.assertFalse(Misconception.objects.filter(source_session=session).exists())

    @patch("tutor.engine.client")
    def test_dismissed_status_survives_a_later_message_in_same_session(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("First hypothesis.")
        session = self._session(self.student, mode=TutorMode.EXPLAIN_MY_MISTAKE)
        engine.send_message(session, "first description")

        misconception = Misconception.objects.get(source_session=session)
        misconception.status = Misconception.Status.DISMISSED
        misconception.save(update_fields=["status"])

        mock_client.messages.create.return_value = _fake_response("Second hypothesis.")
        engine.send_message(session, "another message")

        misconception.refresh_from_db()
        self.assertEqual(misconception.status, Misconception.Status.DISMISSED)
        self.assertEqual(misconception.hypothesis, "Second hypothesis.")

    @patch("tutor.engine.client")
    def test_misconception_captures_session_topic_when_set(self, mock_client):
        strand = Strand.objects.create(school=self.school, subject=self.subject, name="Number", order=1)
        topic = Topic.objects.create(strand=strand, name="Fractions", order=1)
        mock_client.messages.create.return_value = _fake_response("Hypothesis text.")
        session = self._session(self.student, mode=TutorMode.EXPLAIN_MY_MISTAKE, topic=topic)

        engine.send_message(session, "description")

        misconception = Misconception.objects.get(source_session=session)
        self.assertEqual(misconception.topic, topic)
