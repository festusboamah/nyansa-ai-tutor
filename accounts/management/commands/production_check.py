from django.conf import settings
from django.core.checks import run_checks
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Fail unless production security, database, and migration prerequisites are satisfied."

    def handle(self, *args, **options):
        failures = []
        if not settings.IS_PRODUCTION:
            failures.append("DJANGO_ENV must be production.")
        if settings.DEBUG:
            failures.append("DJANGO_DEBUG must be False.")
        if connection.vendor != "postgresql":
            failures.append("The production database must be PostgreSQL.")
        if not settings.ALLOWED_HOSTS:
            failures.append("DJANGO_ALLOWED_HOSTS must not be empty.")
        minimum_secret_length = 32 if settings.NYANSA_DEMO_MODE else 50
        if len(settings.SECRET_KEY) < minimum_secret_length:
            failures.append(
                f"DJANGO_SECRET_KEY must contain at least {minimum_secret_length} characters."
            )
        if not settings.CSRF_TRUSTED_ORIGINS:
            failures.append("DJANGO_CSRF_TRUSTED_ORIGINS must be configured.")
        if not settings.MEDIA_ROOT.is_absolute():
            failures.append("NYANSA_MEDIA_ROOT must resolve to an absolute persistent-storage path.")
        deploy_errors = [item for item in run_checks(include_deployment_checks=True) if item.is_serious()]
        failures.extend(f"{item.id}: {item.msg}" for item in deploy_errors)
        try:
            executor = MigrationExecutor(connection)
            if executor.migration_plan(executor.loader.graph.leaf_nodes()):
                failures.append("Unapplied database migrations remain.")
        except Exception as error:
            failures.append(f"Database migration check failed: {error}")
        if failures:
            raise CommandError("Production readiness failed:\n- " + "\n- ".join(failures))
        self.stdout.write(self.style.SUCCESS("Production readiness checks passed."))
