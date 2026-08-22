from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .client import AIError, complete_json, complete_text


def _fake_response(text):
    return Mock(content=[Mock(text=text)])


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
