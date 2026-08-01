from django.db import migrations, models
import django.db.models.deletion


def copy_lesson_notifications(apps, schema_editor):
    LegacyNotification = apps.get_model("dashboard", "LessonNoteNotification")
    Notification = apps.get_model("communications", "Notification")
    rows = []
    for legacy in LegacyNotification.objects.select_related("lesson_note", "recipient"):
        note = legacy.lesson_note
        target = (
            f"/dashboard/lesson-review/{note.id}/"
            if legacy.recipient.role == "SCHOOL_ADMIN"
            else f"/dashboard/lesson-notes/{note.id}/"
        )
        rows.append(Notification(
            school_id=legacy.recipient.school_id,
            recipient_id=legacy.recipient_id,
            kind="LESSON_REVIEW",
            title="Lesson note update",
            message=legacy.message,
            target_url=target,
            deduplication_key=f"legacy-lesson-alert:{legacy.id}",
            read_at=legacy.read_at,
            created_at=legacy.created_at,
        ))
    Notification.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("communications", "0001_initial"),
        ("dashboard", "0002_lessonnote_current_version_lessonnote_reviewed_at_and_more"),
    ]
    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("LESSON_REVIEW", "Lesson review"), ("GRADE_REVIEW", "Grade review"), ("ASSIGNMENT", "Assignment submission"), ("REPORT_REVIEW", "Report review"), ("FINANCE", "Finance alert"), ("ANALYTICS", "Analytics alert")], max_length=24)),
                ("title", models.CharField(max_length=160)),
                ("message", models.CharField(max_length=500)),
                ("target_url", models.CharField(max_length=300)),
                ("deduplication_key", models.CharField(max_length=180)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="schools.schoolmembership")),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="schools.school")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(fields=("school", "recipient", "deduplication_key"), name="unique_recipient_notification_event"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["recipient", "read_at", "created_at"], name="notification_inbox_idx"),
        ),
        migrations.RunPython(copy_lesson_notifications, migrations.RunPython.noop),
    ]
