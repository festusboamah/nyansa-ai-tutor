import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="School",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                (
                    "slug",
                    models.SlugField(
                        max_length=80,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Use lowercase letters, numbers, and single hyphens only.",
                                regex="^[a-z0-9]+(?:-[a-z0-9]+)*$",
                            )
                        ],
                    ),
                ),
                ("address", models.TextField(blank=True)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("timezone", models.CharField(default="Africa/Accra", max_length=64)),
                ("logo", models.FileField(blank=True, upload_to="schools/logos/")),
                ("official_stamp", models.FileField(blank=True, upload_to="schools/stamps/")),
                (
                    "status",
                    models.CharField(
                        choices=[("ACTIVE", "Active"), ("SUSPENDED", "Suspended"), ("ARCHIVED", "Archived")],
                        default="ACTIVE",
                        max_length=12,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name", "id"]},
        ),
        migrations.CreateModel(
            name="SchoolMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("SCHOOL_ADMIN", "School Admin"),
                            ("TEACHER", "Teacher"),
                            ("STUDENT", "Student"),
                            ("PARENT", "Parent/Guardian"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("INVITED", "Invited"), ("ACTIVE", "Active"), ("SUSPENDED", "Suspended")],
                        default="ACTIVE",
                        max_length=12,
                    ),
                ),
                (
                    "identifier",
                    models.CharField(
                        blank=True,
                        help_text="Optional school-specific staff, student, or guardian identifier.",
                        max_length=50,
                    ),
                ),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="schools.school"),
                ),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="school_memberships", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                "ordering": ["school_id", "user_id"],
                "indexes": [models.Index(fields=["school", "role", "status"], name="school_role_status_idx")],
                "constraints": [models.UniqueConstraint(fields=("school", "user"), name="unique_school_user_membership")],
            },
        ),
    ]
