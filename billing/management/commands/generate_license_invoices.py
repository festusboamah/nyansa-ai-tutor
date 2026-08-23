from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from billing.models import SchoolLicense
from billing.services import generate_invoice


class Command(BaseCommand):
    help = "Generates a LicenseInvoice for every active school license whose billing period has ended, then advances the period. Meant to be run on a schedule (e.g. a daily cron job) - this codebase has no Celery/task runner, so every recurring job here is a plain management command."

    def handle(self, *args, **options):
        today = timezone.localdate()
        licenses = SchoolLicense.objects.filter(
            status=SchoolLicense.Status.ACTIVE, current_period_end__lte=today
        ).select_related("plan", "school")

        created = 0
        for license in licenses:
            period_start = license.current_period_start
            period_end = license.current_period_end
            generate_invoice(school_license=license, period_start=period_start, period_end=period_end)
            created += 1

            license.current_period_start = period_end + timedelta(days=1)
            license.current_period_end = license.current_period_start + timedelta(days=30)
            license.save(update_fields=["current_period_start", "current_period_end"])

        self.stdout.write(f"Generated {created} license invoice(s).")
