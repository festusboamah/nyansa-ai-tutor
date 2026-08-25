from django.core.management.base import BaseCommand

from integrations.models import Suku360RosterCredential
from integrations.suku360_sync import Suku360SyncError, pull_roster
from schools.models import School


class Command(BaseCommand):
    help = (
        "Pulls the roster (academic year, terms, classes, enrollments, "
        "teaching assignments) from Suku360 for every school with an active "
        "Suku360RosterCredential, or one school given by --school-slug. "
        "Meant to be run on a schedule (e.g. a daily cron job) - this "
        "codebase has no Celery/task runner, so every recurring job here is "
        "a plain management command, same as billing's generate_license_invoices."
    )

    def add_arguments(self, parser):
        parser.add_argument("--school-slug", help="Only sync this one school.")

    def handle(self, *args, **options):
        credentials = Suku360RosterCredential.objects.filter(is_active=True).select_related("school")
        slug = options.get("school_slug")
        if slug:
            credentials = credentials.filter(school=School.objects.get(slug=slug))

        for credential in credentials:
            try:
                batch = pull_roster(credential.school)
            except Suku360SyncError as exc:
                self.stderr.write(f"{credential.school}: sync failed - {exc}")
                continue
            self.stdout.write(f"{credential.school}: {batch.get_status_display()} ({batch.records.count()} records)")
