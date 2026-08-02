from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("communications", "0004_notification_archived_at")]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="kind",
            field=models.CharField(
                choices=[
                    ("LESSON_REVIEW", "Lesson review"),
                    ("GRADE_REVIEW", "Grade review"),
                    ("ASSIGNMENT", "Assignment submission"),
                    ("STAFF_ASSIGNMENT", "Teaching assignment"),
                    ("REPORT_REVIEW", "Report review"),
                    ("FINANCE", "Finance alert"),
                    ("ANALYTICS", "Analytics alert"),
                ],
                max_length=24,
            ),
        ),
    ]
