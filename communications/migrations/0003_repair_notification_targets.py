from django.db import migrations


def repair_notification_targets(apps, schema_editor):
    Notification = apps.get_model("communications", "Notification")
    Notification.objects.filter(
        kind="LESSON_REVIEW", recipient__role="SCHOOL_ADMIN"
    ).update(target_url="/dashboard/lesson-review/")
    Notification.objects.filter(
        kind="LESSON_REVIEW", recipient__role="TEACHER"
    ).update(target_url="/dashboard/lesson-notes/")
    Notification.objects.filter(kind="ASSIGNMENT").update(target_url="/dashboard/")
    Notification.objects.filter(kind="REPORT_REVIEW").update(target_url="/reports/")


class Migration(migrations.Migration):
    dependencies = [("communications", "0002_notification")]
    operations = [migrations.RunPython(repair_notification_targets, migrations.RunPython.noop)]
