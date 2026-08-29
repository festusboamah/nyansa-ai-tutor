from django.core.management.base import BaseCommand
from django.utils import timezone

from quizzes.models import Quiz


class Command(BaseCommand):
    help = (
        "Publishes results for exams set to scheduled release once their release time has "
        "passed. Meant to be run on a schedule (e.g. an hourly cron job) - this codebase has "
        "no Celery/task runner, so every recurring job here is a plain management command. "
        "A teacher/admin can always publish manually as a fallback if this doesn't run reliably."
    )

    def handle(self, *args, **options):
        now = timezone.now()
        due = Quiz.objects.filter(
            assessment_type=Quiz.AssessmentType.EXAM,
            results_release_mode=Quiz.ResultsReleaseMode.SCHEDULED,
            results_release_at__lte=now,
            results_published_at__isnull=True,
        )
        count = due.update(results_published_at=now)
        self.stdout.write(f"Released results for {count} exam(s).")
