# Additive schema changes for GES lesson and scheme planning.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0006_remove_lessonnote_num_days_lessonnote_teaching_days"),
    ]

    operations = [
        migrations.AddField(
            model_name="lessonnote",
            name="teacher_name",
            field=models.CharField(
                blank=True,
                help_text="Name printed on the lesson note; defaults to your profile name.",
                max_length=150,
            ),
        ),
        migrations.AddField(
            model_name="schemeoflearning",
            name="academic_year",
            field=models.CharField(
                blank=True, help_text="e.g. 2026/2027", max_length=30
            ),
        ),
        migrations.AddField(
            model_name="schemeoflearning",
            name="plan_type",
            field=models.CharField(
                choices=[("TERMLY", "Termly"), ("YEARLY", "Yearly")],
                default="TERMLY",
                max_length=6,
            ),
        ),
        migrations.AlterField(
            model_name="lessonnote",
            name="content_standard",
            field=models.TextField(
                blank=True,
                help_text="Optional - selected from the supplied NaCCA curriculum where available.",
            ),
        ),
        migrations.AlterField(
            model_name="lessonnote",
            name="learning_indicator",
            field=models.TextField(
                blank=True,
                help_text="Optional - selected from the supplied NaCCA curriculum. You can enter a specific indicator code and wording.",
            ),
        ),
    ]
