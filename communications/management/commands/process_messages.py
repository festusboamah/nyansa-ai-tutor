from django.core.management.base import BaseCommand

from communications.services import process_queued_messages


class Command(BaseCommand):
    help = "Process queued email and SMS communication intents."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        processed = process_queued_messages(limit=max(1, options["limit"]))
        sent = sum(item.status == item.Status.SENT for item in processed)
        failed = len(processed) - sent
        self.stdout.write(self.style.SUCCESS(f"Processed {len(processed)} message(s): {sent} sent, {failed} failed."))
