import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("courses", "0005_backfill_legacy_school")]

    operations = [
        migrations.AlterField(
            model_name="subject",
            name="school",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subjects",
                to="schools.school",
            ),
        ),
        migrations.AlterField(
            model_name="studydocument",
            name="school",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="study_documents",
                to="schools.school",
            ),
        ),
        migrations.AddIndex(
            model_name="subject",
            index=models.Index(fields=["school", "name"], name="subject_school_name_idx"),
        ),
    ]
