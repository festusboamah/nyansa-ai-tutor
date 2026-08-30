import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from django.core.mail import EmailMultiAlternatives, send_mail
from django.test import SimpleTestCase, override_settings


@override_settings(
    EMAIL_BACKEND="config.email_backends.ResendEmailBackend",
    RESEND_API_KEY="re_test_key",
    RESEND_API_URL="https://api.resend.test/emails",
    EMAIL_TIMEOUT=4,
    DEFAULT_FROM_EMAIL="Nyansa <noreply@nyansa.app>",
)
class ResendEmailBackendTests(SimpleTestCase):
    @patch("config.email_backends.urlopen")
    def test_send_mail_posts_expected_payload(self, urlopen):
        response = MagicMock(status=200)
        urlopen.return_value.__enter__.return_value = response

        sent = send_mail(
            "Reset your Nyansa password",
            "Use this secure link.",
            None,
            ["learner@example.com"],
        )

        self.assertEqual(sent, 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 4)
        self.assertEqual(request.get_header("Authorization"), "Bearer re_test_key")
        self.assertEqual(
            json.loads(request.data),
            {
                "from": "Nyansa <noreply@nyansa.app>",
                "to": ["learner@example.com"],
                "subject": "Reset your Nyansa password",
                "text": "Use this secure link.",
            },
        )

    @patch("config.email_backends.urlopen")
    def test_html_alternative_and_reply_to_are_preserved(self, urlopen):
        urlopen.return_value.__enter__.return_value = MagicMock(status=200)
        message = EmailMultiAlternatives(
            "School invitation",
            "You have been invited.",
            None,
            ["teacher@example.com"],
            reply_to=["support@nyansa.app"],
        )
        message.attach_alternative("<p>You have been invited.</p>", "text/html")

        self.assertEqual(message.send(), 1)
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(payload["html"], "<p>You have been invited.</p>")
        self.assertEqual(payload["reply_to"], ["support@nyansa.app"])

    @patch("config.email_backends.urlopen", side_effect=URLError("temporary failure"))
    def test_delivery_error_is_raised_by_default(self, urlopen):
        with self.assertRaises(URLError):
            send_mail("Subject", "Body", None, ["learner@example.com"])

    @override_settings(RESEND_API_KEY="")
    def test_missing_api_key_fails_clearly(self):
        with self.assertRaisesMessage(Exception, "RESEND_API_KEY must be configured"):
            send_mail("Subject", "Body", None, ["learner@example.com"])
