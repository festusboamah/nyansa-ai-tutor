from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("attendance", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="attendancerecord",
            name="reason",
            field=models.CharField(
                blank=True,
                help_text="Optional explanation for an absence or excused absence.",
                max_length=300,
            ),
        ),
    ]
