from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("schools", "0004_school_education_levels")]
    operations = [
        migrations.AddField(
            model_name="school",
            name="stream_structure",
            field=models.CharField(
                choices=[("SINGLE", "Single stream"), ("DOUBLE", "Double stream (A and B)")],
                default="SINGLE", max_length=8,
            ),
        ),
    ]
