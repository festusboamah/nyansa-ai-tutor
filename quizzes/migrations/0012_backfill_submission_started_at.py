from django.db import migrations
from django.db.models import F


def backfill_started_at(apps, schema_editor):
    Submission = apps.get_model("quizzes", "Submission")
    Submission.objects.filter(submitted_at__isnull=False).update(started_at=F("submitted_at"))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("quizzes", "0011_answer_ai_suggested_feedback_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_started_at, noop),
    ]
