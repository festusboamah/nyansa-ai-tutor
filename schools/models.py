from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from datetime import timedelta


def default_invitation_expiry():
    return timezone.now() + timedelta(days=7)


class School(models.Model):
    class EducationSystem(models.TextChoices):
        BASIC = "BASIC", "Basic School"
        SENIOR_HIGH = "SENIOR_HIGH", "Senior High School"
        CAMBRIDGE = "CAMBRIDGE", "Cambridge International"
        TERTIARY = "TERTIARY", "Tertiary"

    class StudentAccessMode(models.TextChoices):
        STAFF_MANAGED = "STAFF_MANAGED", "Staff-managed records"
        PORTAL = "PORTAL", "Student accounts and online learning"
        HYBRID = "HYBRID", "Hybrid"

    class StreamStructure(models.TextChoices):
        SINGLE = "SINGLE", "Single stream"
        DOUBLE = "DOUBLE", "Double stream (A and B)"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        ARCHIVED = "ARCHIVED", "Archived"

    name = models.CharField(max_length=200)
    education_system = models.CharField(
        max_length=16,
        choices=EducationSystem.choices,
        default=EducationSystem.BASIC,
        help_text="The curriculum and grading standard this school follows.",
    )
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
    suku360_id = models.CharField(
        max_length=64, blank=True, null=True, unique=True, db_index=True,
        help_text="Suku360's own school id, once synced. Nyansa-local until then.",
    )
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    timezone = models.CharField(max_length=64, default="Africa/Accra")
    student_access_mode = models.CharField(
        max_length=16,
        choices=StudentAccessMode.choices,
        default=StudentAccessMode.STAFF_MANAGED,
    )
    offers_kg = models.BooleanField(default=False)
    offers_primary = models.BooleanField(default=True)
    offers_jhs = models.BooleanField(default=False)
    offers_shs = models.BooleanField(default=False, help_text="General Senior High School (SHS 1-3).")
    offers_stem = models.BooleanField(
        default=False, help_text="A dedicated STEM-focused senior high programme, distinct from general SHS.",
    )
    offers_tvet = models.BooleanField(
        default=False,
        help_text="Technical and Vocational Education and Training - a separate institution type from SHS/STEM.",
    )
    stream_structure = models.CharField(
        max_length=8, choices=StreamStructure.choices, default=StreamStructure.SINGLE
    )
    logo = models.FileField(upload_to="schools/logos/", blank=True)
    official_stamp = models.FileField(upload_to="schools/stamps/", blank=True)
    headteacher_name = models.CharField(max_length=160, blank=True)
    headteacher_signature = models.FileField(upload_to="schools/signatures/", blank=True)
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
    suku360_id = models.CharField(
        max_length=64, blank=True, null=True, db_index=True,
        help_text="Suku360's own Membership/Student id for this person at this school, once synced.",
    )
    portal_access_enabled = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "user"], name="unique_school_user_membership"),
            models.UniqueConstraint(
                fields=["school", "identifier"],
                condition=models.Q(identifier__gt=""),
                name="unique_school_member_identifier",
            ),
            models.UniqueConstraint(
                fields=["school", "suku360_id"],
                condition=models.Q(suku360_id__isnull=False),
                name="unique_school_member_suku360_id",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "role", "status"], name="school_role_status_idx")
        ]
        ordering = ["school_id", "user_id"]

    def __str__(self):
        return f"{self.user.username} at {self.school} ({self.get_role_display()})"

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE and self.school.status == School.Status.ACTIVE


class StudentProfile(models.Model):
    class Gender(models.TextChoices):
        FEMALE = "FEMALE", "Female"
        MALE = "MALE", "Male"
        OTHER = "OTHER", "Other / not specified"

    membership = models.OneToOneField(
        SchoolMembership, on_delete=models.CASCADE, related_name="student_profile"
    )
    gender = models.CharField(max_length=12, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    guardian_name = models.CharField(max_length=160, blank=True)
    guardian_phone = models.CharField(max_length=30, blank=True)

    def clean(self):
        if self.membership_id and self.membership.role != SchoolMembership.Role.STUDENT:
            from django.core.exceptions import ValidationError
            raise ValidationError("Student profiles require a student membership.")


class SchoolInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        REVOKED = "REVOKED", "Revoked"
        EXPIRED = "EXPIRED", "Expired"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=SchoolMembership.Role.choices)
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="school_invitations_sent")
    expires_at = models.DateTimeField(default=default_invitation_expiry)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["school", "email"], condition=models.Q(status="PENDING"), name="one_pending_invite_per_school_email")]

    @property
    def is_usable(self):
        return self.status == self.Status.PENDING and self.expires_at > timezone.now()
