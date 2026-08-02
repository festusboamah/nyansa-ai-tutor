import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("schools", "0002_schoolinvitation")]
    operations = [
        migrations.AddField(
            model_name="school",
            name="student_access_mode",
            field=models.CharField(
                choices=[("STAFF_MANAGED", "Staff-managed records"), ("PORTAL", "Student accounts and online learning"), ("HYBRID", "Hybrid")],
                default="STAFF_MANAGED", max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="schoolmembership",
            name="portal_access_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="StudentProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("gender", models.CharField(blank=True, choices=[("FEMALE", "Female"), ("MALE", "Male"), ("OTHER", "Other / not specified")], max_length=12)),
                ("date_of_birth", models.DateField(blank=True, null=True)),
                ("guardian_name", models.CharField(blank=True, max_length=160)),
                ("guardian_phone", models.CharField(blank=True, max_length=30)),
                ("membership", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="student_profile", to="schools.schoolmembership")),
            ],
        ),
        migrations.AddConstraint(
            model_name="schoolmembership",
            constraint=models.UniqueConstraint(
                condition=models.Q(("identifier__gt", "")),
                fields=("school", "identifier"),
                name="unique_school_member_identifier",
            ),
        ),
    ]
