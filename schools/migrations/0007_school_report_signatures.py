from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("schools", "0005_school_stream_structure")]

    operations = [
        migrations.AddField(
            model_name="school",
            name="headteacher_name",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="school",
            name="headteacher_signature",
            field=models.FileField(blank=True, upload_to="schools/signatures/"),
        ),
    ]
