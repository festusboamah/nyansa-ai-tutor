from django.db import models


class Suku360RosterCredential(models.Model):
    """The Bearer token Suku360 issued to Nyansa for one school (the
    opposite direction from IntegrationCredential below, which is the
    token Nyansa issues so Suku360/other partners can read Nyansa data).
    Stored so it can be sent outbound - not hashed, since a hash can't be
    turned back into the header value a real HTTP call needs."""

    school = models.OneToOneField(
        "schools.School", on_delete=models.CASCADE, related_name="suku360_roster_credential"
    )
    token = models.CharField(max_length=128)
    base_url = models.URLField(help_text="Suku360 API base URL, e.g. https://api.suku360.com")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Suku360 roster credential for {self.school.name}"


class SyncBatch(models.Model):
    """One pull_roster() run for one school. Mirrors
    gradebook.GradeImportBatch's role: a single auditable record of 'what
    happened when this ran', with SyncRecord rows underneath it for the
    per-entity detail - the pattern docs/suku360-inbound-sync-design.md
    proposed before a real Suku360 existed to sync against."""

    class Status(models.TextChoices):
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="sync_batches")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROCESSING)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Suku360 sync for {self.school.name} ({self.get_status_display()})"


class SyncRecord(models.Model):
    """One upserted (or failed) entity within a SyncBatch."""

    class EntityType(models.TextChoices):
        ACADEMIC_YEAR = "ACADEMIC_YEAR", "Academic Year"
        TERM = "TERM", "Term"
        SCHOOL_CLASS = "SCHOOL_CLASS", "School Class"
        STUDENT = "STUDENT", "Student"
        TEACHER = "TEACHER", "Teacher"
        ENROLLMENT = "ENROLLMENT", "Class Enrollment"
        TEACHER_ASSIGNMENT = "TEACHER_ASSIGNMENT", "Teacher Assignment"

    class Action(models.TextChoices):
        CREATED = "CREATED", "Created"
        UPDATED = "UPDATED", "Updated"
        UNCHANGED = "UNCHANGED", "Unchanged"
        ERROR = "ERROR", "Error"

    batch = models.ForeignKey(SyncBatch, on_delete=models.CASCADE, related_name="records")
    entity_type = models.CharField(max_length=20, choices=EntityType.choices)
    suku360_id = models.CharField(max_length=64)
    nyansa_object_id = models.CharField(max_length=32, blank=True)
    action = models.CharField(max_length=10, choices=Action.choices)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.entity_type} {self.suku360_id} ({self.action})"


class IntegrationCredential(models.Model):
    """One active API credential per school. Regenerating replaces the token,
    immediately invalidating the previous one - only the SHA-256 hash of the
    plaintext token is ever stored; the plaintext is shown once at creation."""

    school = models.OneToOneField(
        "schools.School", on_delete=models.CASCADE, related_name="integration_credential"
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    created_by = models.ForeignKey("schools.SchoolMembership", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"API credential for {self.school.name}"
