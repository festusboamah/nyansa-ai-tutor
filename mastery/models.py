from django.core.exceptions import ValidationError
from django.db import models


class Strand(models.Model):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="strands")
    subject = models.ForeignKey("courses.Subject", on_delete=models.CASCADE, related_name="strands")
    name = models.CharField(max_length=120)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["subject", "name"], name="unique_subject_strand")]
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.subject.name} · {self.name}"


class Topic(models.Model):
    strand = models.ForeignKey(Strand, on_delete=models.CASCADE, related_name="topics")
    name = models.CharField(max_length=120)
    order = models.PositiveIntegerField(default=0)
    prerequisites = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="unlocks"
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["strand", "name"], name="unique_strand_topic")]
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.strand.name} · {self.name}"


class TopicRevision(models.Model):
    topic = models.ForeignKey(Topic, on_delete=models.PROTECT, related_name="revisions")
    previous_name = models.CharField(max_length=120)
    new_name = models.CharField(max_length=120)
    previous_strand_name = models.CharField(max_length=120)
    new_strand_name = models.CharField(max_length=120)
    reason = models.CharField(max_length=300)
    changed_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="topic_revisions"
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at", "-id"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Topic revision history is immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Topic revision history is immutable.")

    def __str__(self):
        return f"{self.topic} · {self.changed_at:%Y-%m-%d}"


class Misconception(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        DISMISSED = "DISMISSED", "Dismissed"
        RESOLVED = "RESOLVED", "Resolved"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="misconceptions")
    student = models.ForeignKey("schools.SchoolMembership", on_delete=models.CASCADE, related_name="misconceptions")
    topic = models.ForeignKey(
        Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name="misconceptions"
    )
    source_session = models.OneToOneField(
        "tutor.TutorSession", on_delete=models.SET_NULL, null=True, blank=True, related_name="misconception"
    )
    student_description = models.TextField()
    hypothesis = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    reviewed_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_misconceptions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} · {self.hypothesis[:50]}"


class RemediationPlan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="remediation_plans")
    student = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.CASCADE, related_name="remediation_plans"
    )
    topic = models.ForeignKey(
        Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name="remediation_plans"
    )
    term = models.ForeignKey("academics.Term", on_delete=models.CASCADE, related_name="remediation_plans")
    plan = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    mastery_percentage_at_start = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    mastery_percentage_at_completion = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    outcome = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.CASCADE, related_name="created_remediation_plans"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} · {self.topic.name if self.topic else 'deleted topic'}"


class StudyGoal(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ACHIEVED = "ACHIEVED", "Achieved"
        ABANDONED = "ABANDONED", "Abandoned"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="study_goals")
    student = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.CASCADE, related_name="study_goals"
    )
    topic = models.ForeignKey(
        Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name="study_goals"
    )
    note = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    achieved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} · {self.topic.name if self.topic else 'deleted topic'}"
