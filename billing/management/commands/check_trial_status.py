from django.core.management.base import BaseCommand

from billing.services import check_trial_statuses


class Command(BaseCommand):
    help = (
        "Sends a reminder notification as a school's trial approaches its end, and "
        "moves an already-ended trial to PAST_DUE. Meant to run daily - this codebase "
        "has no Celery/task runner, so every recurring job here is a plain management "
        "command (same pattern as generate_license_invoices/release_exam_results)."
    )

    def handle(self, *args, **options):
        result = check_trial_statuses()
        self.stdout.write(
            f"Sent {result['reminded']} trial-ending reminder(s), "
            f"moved {result['expired']} trial(s) to past-due."
        )
