from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from schools.models import School, SchoolMembership

from .client import AIError, complete_json, complete_text
from .models import AIUsageEvent


def _fake_response(text, input_tokens=10, output_tokens=20):
    return Mock(content=[Mock(text=text)], usage=Mock(input_tokens=input_tokens, output_tokens=output_tokens))


class CompleteTextTests(SimpleTestCase):
    @patch("ai_core.client.client")
    def test_returns_stripped_response_text(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("  Hello there.  ")
        result = complete_text("prompt", max_tokens=100)
        self.assertEqual(result, "Hello there.")

    @patch("ai_core.client.client")
    def test_raises_ai_error_on_api_failure(self, mock_client):
        mock_client.messages.create.side_effect = RuntimeError("upstream is down")
        with self.assertRaises(AIError):
            complete_text("prompt", max_tokens=100)

    @patch("ai_core.client.client")
    def test_model_defaults_to_settings_value(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("ok")
        complete_text("prompt", max_tokens=100)
        self.assertEqual(mock_client.messages.create.call_args.kwargs["model"], "claude-sonnet-4-5")

    @patch("ai_core.client.client")
    def test_explicit_model_overrides_default(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("ok")
        complete_text("prompt", max_tokens=100, model="claude-other-model")
        self.assertEqual(mock_client.messages.create.call_args.kwargs["model"], "claude-other-model")


class CompleteJsonTests(SimpleTestCase):
    @patch("ai_core.client.client")
    def test_parses_plain_json(self, mock_client):
        mock_client.messages.create.return_value = _fake_response('{"score": 5}')
        self.assertEqual(complete_json("prompt", max_tokens=100), {"score": 5})

    @patch("ai_core.client.client")
    def test_strips_bare_code_fence(self, mock_client):
        mock_client.messages.create.return_value = _fake_response('```\n{"score": 5}\n```')
        self.assertEqual(complete_json("prompt", max_tokens=100), {"score": 5})

    @patch("ai_core.client.client")
    def test_strips_json_labelled_code_fence(self, mock_client):
        mock_client.messages.create.return_value = _fake_response('```json\n{"score": 5}\n```')
        self.assertEqual(complete_json("prompt", max_tokens=100), {"score": 5})

    @patch("ai_core.client.client")
    def test_raises_ai_error_on_malformed_json(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("not json at all")
        with self.assertRaises(AIError):
            complete_json("prompt", max_tokens=100)

    @patch("ai_core.client.client")
    def test_raises_ai_error_on_api_failure(self, mock_client):
        mock_client.messages.create.side_effect = RuntimeError("upstream is down")
        with self.assertRaises(AIError):
            complete_json("prompt", max_tokens=100)


class UsageLoggingTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Usage School", slug="usage-school")

    @patch("ai_core.client.client")
    def test_successful_call_logs_usage_event(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("ok", input_tokens=100, output_tokens=200)

        complete_text("prompt", max_tokens=100, school=self.school, source=AIUsageEvent.Source.STUDY_AI)

        event = AIUsageEvent.objects.get(school=self.school)
        self.assertTrue(event.succeeded)
        self.assertEqual(event.input_tokens, 100)
        self.assertEqual(event.output_tokens, 200)
        self.assertEqual(event.source, AIUsageEvent.Source.STUDY_AI)

    @patch("ai_core.client.client")
    def test_failed_call_logs_failure_event(self, mock_client):
        mock_client.messages.create.side_effect = RuntimeError("upstream is down")

        with self.assertRaises(AIError):
            complete_text("prompt", max_tokens=100, school=self.school, source=AIUsageEvent.Source.LESSON_AI)

        event = AIUsageEvent.objects.get(school=self.school)
        self.assertFalse(event.succeeded)
        self.assertIn("upstream is down", event.error_message)

    @patch("ai_core.client.client")
    def test_call_without_school_does_not_log_anything(self, mock_client):
        mock_client.messages.create.return_value = _fake_response("ok")

        complete_text("prompt", max_tokens=100)

        self.assertFalse(AIUsageEvent.objects.exists())

    @override_settings(AI_DAILY_TOKEN_CAP_PER_SCHOOL=250)
    @patch("ai_core.client.client")
    def test_daily_cap_blocks_further_calls_without_hitting_the_api(self, mock_client):
        AIUsageEvent.objects.create(
            school=self.school, source=AIUsageEvent.Source.STUDY_AI, model="claude-sonnet-4-5",
            input_tokens=150, output_tokens=150, succeeded=True,
        )

        with self.assertRaises(AIError):
            complete_text("prompt", max_tokens=100, school=self.school, source=AIUsageEvent.Source.STUDY_AI)

        mock_client.messages.create.assert_not_called()


class AIUsageReportViewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Report School", slug="report-school")
        self.admin = User.objects.create_user(username="usage-admin", password="test-password")
        SchoolMembership.objects.create(
            school=self.school, user=self.admin, role=SchoolMembership.Role.SCHOOL_ADMIN
        )
        self.teacher = User.objects.create_user(
            username="usage-teacher", password="test-password", role=User.Role.TEACHER
        )
        SchoolMembership.objects.create(
            school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER
        )

    def test_school_admin_can_view_usage_report(self):
        AIUsageEvent.objects.create(
            school=self.school, source=AIUsageEvent.Source.STUDY_AI, model="claude-sonnet-4-5",
            input_tokens=1000, output_tokens=2000, succeeded=True,
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("ai_usage_report"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Self-Study Hub")

    def test_teacher_cannot_view_usage_report(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("ai_usage_report"), secure=True)

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
