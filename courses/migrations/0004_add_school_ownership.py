import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0001_initial"),
        ("courses", "0003_studydocument_studyquestion"),
    ]

    operations = [
        migrations.AddField(
            model_name="subject",
            name="school",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subjects",
                to="schools.school",
            ),
        ),
        migrations.AddField(
            model_name="studydocument",
            name="school",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="study_documents",
                to="schools.school",
            ),
        ),
    ]
