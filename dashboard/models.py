from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
from courses.models import Subject


class LessonNote(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"
        SENT_BACK = "SENT_BACK", "Sent Back"
        APPROVED = "APPROVED", "Approved"

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lesson_notes"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="lesson_notes"
    )
    class_level = models.CharField(max_length=100, help_text="e.g. Basic 5, JHS 2")
    week_ending = models.DateField()
    strand_topic = models.CharField(max_length=200, help_text="e.g. Numbers, Reproduction")
    content_standard = models.TextField(blank=True)
    learning_indicator = models.TextField()
    performance_indicator = models.TextField(blank=True)
    reference = models.CharField(max_length=300, blank=True)
    resources = models.CharField(max_length=300, blank=True)
    num_days = models.PositiveIntegerField(default=5)
    generated_content = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    current_version = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "schools.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_lesson_notes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    EDITABLE_FIELDS = (
        "subject_id", "class_level", "week_ending", "strand_topic", "content_standard",
        "learning_indicator", "performance_indicator", "reference", "resources", "num_days",
        "generated_content",
    )

    def clean(self):
        if self.reviewed_by_id and (
            self.reviewed_by.school_id != self.subject.school_id
            or self.reviewed_by.role != "SCHOOL_ADMIN"
        ):
            raise ValidationError("Lesson-note reviewer must be an administrator in the same school.")

    def save(self, *args, allow_approved_reopen=False, **kwargs):
        if self.pk:
            previous = LessonNote.objects.filter(pk=self.pk).first()
            if previous and previous.status == self.Status.APPROVED:
                content_changed = any(getattr(previous, field) != getattr(self, field) for field in self.EDITABLE_FIELDS)
                valid_reopen = allow_approved_reopen and not content_changed and self.status == self.Status.SENT_BACK
                if content_changed or self.status != previous.status:
                    if not valid_reopen:
                        raise ValidationError("Approved lesson notes are locked until an administrator reopens them.")
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subject.name} - {self.strand_topic} ({self.week_ending})"


class LessonNoteVersion(models.Model):
    lesson_note = models.ForeignKey(LessonNote, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    snapshot = models.JSONField()
    reason = models.CharField(max_length=500)
    created_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="lesson_note_versions"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(fields=["lesson_note", "version_number"], name="unique_lesson_note_version")
        ]

    def clean(self):
        if self.lesson_note_id and self.created_by_id and (
            self.created_by.school_id != self.lesson_note.subject.school_id
            or self.created_by.user_id != self.lesson_note.teacher_id
        ):
            raise ValidationError("Lesson-note version author must be the note author in the same school.")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Lesson-note versions are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Lesson-note versions are immutable.")


class LessonNoteEvent(models.Model):
    class EventType(models.TextChoices):
        COMMENT = "COMMENT", "Comment"
        SUBMITTED = "SUBMITTED", "Submitted"
        SENT_BACK = "SENT_BACK", "Sent Back"
        APPROVED = "APPROVED", "Approved"
        REOPENED = "REOPENED", "Reopened"
        REVISED = "REVISED", "Revised"

    lesson_note = models.ForeignKey(LessonNote, on_delete=models.PROTECT, related_name="events")
    event_type = models.CharField(max_length=10, choices=EventType.choices)
    message = models.TextField(blank=True)
    actor = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="lesson_note_events"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def clean(self):
        if self.lesson_note_id and self.actor_id and self.actor.school_id != self.lesson_note.subject.school_id:
            raise ValidationError("Lesson-note event actor must belong to the same school.")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Lesson-note workflow history is immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Lesson-note workflow history is immutable.")


class LessonNoteNotification(models.Model):
    lesson_note = models.ForeignKey(LessonNote, on_delete=models.CASCADE, related_name="notifications")
    recipient = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.CASCADE, related_name="lesson_note_notifications"
    )
    message = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def clean(self):
        if self.lesson_note_id and self.recipient_id and self.recipient.school_id != self.lesson_note.subject.school_id:
            raise ValidationError("Lesson-note notification recipient must belong to the same school.")
