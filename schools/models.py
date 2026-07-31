from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


class School(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        ARCHIVED = "ARCHIVED", "Archived"

    name = models.CharField(max_length=200)
    slug = models.SlugField(
        max_length=80,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
                message="Use lowercase letters, numbers, and single hyphens only.",
            )
        ],
    )
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    timezone = models.CharField(max_length=64, default="Africa/Accra")
    logo = models.FileField(upload_to="schools/logos/", blank=True)
    official_stamp = models.FileField(upload_to="schools/stamps/", blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class SchoolMembership(models.Model):
    class Role(models.TextChoices):
        SCHOOL_ADMIN = "SCHOOL_ADMIN", "School Admin"
        TEACHER = "TEACHER", "Teacher"
        STUDENT = "STUDENT", "Student"
        PARENT = "PARENT", "Parent/Guardian"

    class Status(models.TextChoices):
        INVITED = "INVITED", "Invited"
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="school_memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    identifier = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional school-specific staff, student, or guardian identifier.",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "user"], name="unique_school_user_membership")
        ]
        indexes = [
            models.Index(fields=["school", "role", "status"], name="school_role_status_idx")
        ]
        ordering = ["school_id", "user_id"]

    def __str__(self):
        return f"{self.user} at {self.school} ({self.get_role_display()})"

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE and self.school.status == School.Status.ACTIVE
