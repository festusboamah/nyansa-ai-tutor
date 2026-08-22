from django.db import migrations


def rename_low_attendance(apps, schema_editor):
    EarlyWarningPolicy = apps.get_model("analytics", "EarlyWarningPolicy")
    EarlyWarningPolicy.objects.filter(metric="LOW_ATTENDANCE").update(metric="LOW_SUBMISSION_RATE")


def restore_low_attendance(apps, schema_editor):
    EarlyWarningPolicy = apps.get_model("analytics", "EarlyWarningPolicy")
    EarlyWarningPolicy.objects.filter(metric="LOW_SUBMISSION_RATE").update(metric="LOW_ATTENDANCE")


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0002_alter_earlywarningpolicy_metric"),
    ]

    operations = [
        migrations.RunPython(rename_low_attendance, restore_low_attendance),
    ]
