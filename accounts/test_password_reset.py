import re

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

User = get_user_model()


class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="forgetful-teacher", email="forgetful@example.com", password="original-password",
        )

    def test_login_page_links_to_password_reset(self):
        response = self.client.get(reverse("login"), secure=True)
        self.assertContains(response, reverse("password_reset"))

    def test_request_with_known_email_sends_reset_link(self):
        response = self.client.post(
            reverse("password_reset"), {"email": "forgetful@example.com"}, secure=True, follow=True,
        )

        self.assertContains(response, "Check your email")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("forgetful@example.com", mail.outbox[0].to)
        self.assertIn("Reset your Nyansa password", mail.outbox[0].subject)
        match = re.search(r"https?://[^\s]+/accounts/reset/[^\s]+", mail.outbox[0].body)
        self.assertIsNotNone(match, "Expected a reset link in the email body")

    def test_request_with_unknown_email_does_not_leak_and_sends_nothing(self):
        response = self.client.post(
            reverse("password_reset"), {"email": "nobody@example.com"}, secure=True, follow=True,
        )

        self.assertContains(response, "Check your email")
        self.assertEqual(len(mail.outbox), 0)

    def test_full_reset_flow_changes_password(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        # First GET on the real token redirects to a session-stored one-time-use link
        # (Django's own anti-token-leak-via-referer-header design) - follow it.
        response = self.client.get(
            reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token}), secure=True, follow=True,
        )
        self.assertContains(response, "Set a new password")
        confirm_url = response.redirect_chain[-1][0]

        response = self.client.post(
            confirm_url,
            {"new_password1": "a-brand-new-password-99", "new_password2": "a-brand-new-password-99"},
            secure=True, follow=True,
        )
        self.assertContains(response, "Password changed")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("a-brand-new-password-99"))

        logged_in = self.client.login(username="forgetful-teacher", password="a-brand-new-password-99")
        self.assertTrue(logged_in)

    def test_invalid_token_shows_expired_message_not_the_form(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.get(
            reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": "bad-token"}),
            secure=True, follow=True,
        )
        self.assertContains(response, "Link expired")
