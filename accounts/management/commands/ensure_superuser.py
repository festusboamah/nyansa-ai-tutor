import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Idempotently ensures a real Django admin superuser exists, from private "
        "environment variables (DJANGO_SUPERUSER_USERNAME/_EMAIL/_PASSWORD). Safe to "
        "run on every startup: does nothing if the variables aren't set, and never "
        "touches an already-existing account (so a password changed since deploy "
        "isn't silently reset)."
    )

    def handle(self, *args, **options):
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "").strip()
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "")
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "").strip()

        if not username or not password:
            self.stdout.write("Superuser credentials are not configured; skipping.")
            return
        if len(password) < 12:
            raise CommandError("DJANGO_SUPERUSER_PASSWORD must contain at least 12 characters.")

        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Superuser '{username}' already exists; leaving it untouched.")
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(f"Created superuser '{username}'.")
