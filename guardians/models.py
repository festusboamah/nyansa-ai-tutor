from django.core.exceptions import ValidationError
from django.db import models


class GuardianLink(models.Model):
    class Relationship(models.TextChoices):
        MOTHER = "MOTHER", "Mother"
        FATHER = "FATHER", "Father"
        GUARDIAN = "GUARDIAN", "Guardian"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        REVOKED = "REVOKED", "Revoked"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="guardian_links")
    guardian = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.CASCADE, related_name="guardian_links"
    )
    student = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.CASCADE, related_name="student_guardian_links"
    )
    relationship = models.CharField(max_length=10, choices=Relationship.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    is_primary_contact = models.BooleanField(default=False)
    authorization_reference = models.CharField(
        max_length=120, help_text="School-held consent or verification reference."
    )
    authorized_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="authorized_guardian_links"
    )
    authorized_at = models.DateTimeField(auto_now_add=True)
    revoked_by = models.ForeignKey(
        "schools.SchoolMembership", null=True, blank=True, on_delete=models.PROTECT,
        related_name="revoked_guardian_links",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["student__user__last_name", "guardian__user__last_name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "guardian", "student"], name="unique_guardian_student_link")
        ]
        indexes = [models.Index(fields=["school", "guardian", "status"], name="guardian_access_idx")]

    def clean(self):
        errors = {}
        if self.guardian_id and (
            self.guardian.school_id != self.school_id or self.guardian.role != "PARENT"
        ):
            errors["guardian"] = "Guardian must be a parent membership in this school."
        if self.student_id and (
            self.student.school_id != self.school_id or self.student.role != "STUDENT"
        ):
            errors["student"] = "Student must be a student membership in this school."
        for field in ("authorized_by", "revoked_by"):
            actor = getattr(self, field, None)
            if actor and (actor.school_id != self.school_id or actor.role != "SCHOOL_ADMIN"):
                errors[field] = "Guardian-link authorization requires an administrator in this school."
        if not self.authorization_reference.strip():
            errors["authorization_reference"] = "A verification reference is required."
        if errors:
            raise ValidationError(errors)

    @property
    def grants_access(self):
        return self.status == self.Status.ACTIVE and self.guardian.is_active and self.student.is_active

