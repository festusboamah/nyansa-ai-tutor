from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

User = get_user_model()


class EnsureSuperuserCommandTests(TestCase):
    def test_skips_silently_when_not_configured(self):
        call_command("ensure_superuser")
        self.assertFalse(User.objects.filter(is_superuser=True).exists())

    @patch.dict(
        "os.environ",
        {
            "DJANGO_SUPERUSER_USERNAME": "site-admin",
            "DJANGO_SUPERUSER_PASSWORD": "a-safe-long-password",
            "DJANGO_SUPERUSER_EMAIL": "admin@example.com",
        },
    )
    def test_creates_superuser_when_configured(self):
        call_command("ensure_superuser")

        user = User.objects.get(username="site-admin")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password("a-safe-long-password"))

    @patch.dict(
        "os.environ",
        {
            "DJANGO_SUPERUSER_USERNAME": "site-admin",
            "DJANGO_SUPERUSER_PASSWORD": "a-safe-long-password",
        },
    )
    def test_is_idempotent_and_does_not_touch_existing_account(self):
        call_command("ensure_superuser")
        user = User.objects.get(username="site-admin")
        user.set_password("a-different-password-set-later")
        user.save(update_fields=["password"])

        call_command("ensure_superuser")

        user.refresh_from_db()
        self.assertTrue(user.check_password("a-different-password-set-later"))

    @patch.dict(
        "os.environ",
        {"DJANGO_SUPERUSER_USERNAME": "site-admin", "DJANGO_SUPERUSER_PASSWORD": "too-short"},
    )
    def test_rejects_a_short_password(self):
        with self.assertRaisesMessage(CommandError, "12 characters"):
            call_command("ensure_superuser")
