from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class EarlyWarningPolicy(models.Model):
    class Metric(models.TextChoices):
        LOW_AVERAGE = "LOW_AVERAGE", "Low academic average"
        LOW_ATTENDANCE = "LOW_ATTENDANCE", "Low attendance percentage"
        MISSING_GRADES = "MISSING_GRADES", "Missing approved grade entries"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="warning_policies")
    name = models.CharField(max_length=120)
    metric = models.CharField(max_length=20, choices=Metric.choices)
    threshold = models.DecimalField(
        max_digits=6, decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="created_warning_policies"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "name"], name="unique_school_warning_policy")]

    def clean(self):
        if self.created_by_id and (
            self.created_by.school_id != self.school_id or self.created_by.role != "SCHOOL_ADMIN"
        ):
            raise ValidationError("Warning policy creator must be an administrator in the same school.")


class RiskSignal(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
        RESOLVED = "RESOLVED", "Resolved"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="risk_signals")
    policy = models.ForeignKey(EarlyWarningPolicy, on_delete=models.PROTECT, related_name="signals")
    student = models.ForeignKey("schools.SchoolMembership", on_delete=models.PROTECT, related_name="risk_signals")
    school_class = models.ForeignKey("academics.SchoolClass", on_delete=models.PROTECT, related_name="risk_signals")
    term = models.ForeignKey("academics.Term", on_delete=models.PROTECT, related_name="risk_signals")
    observed_value = models.DecimalField(max_digits=8, decimal_places=2)
    evidence = models.JSONField(default=dict)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.OPEN)
    generated_at = models.DateTimeField(auto_now=True)
    acknowledged_by = models.ForeignKey(
        "schools.SchoolMembership", null=True, blank=True, on_delete=models.PROTECT,
        related_name="acknowledged_risk_signals",
    )
    resolved_by = models.ForeignKey(
        "schools.SchoolMembership", null=True, blank=True, on_delete=models.PROTECT,
        related_name="resolved_risk_signals",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["policy", "student", "school_class", "term"], name="unique_student_policy_signal")
        ]
        indexes = [models.Index(fields=["school", "status", "term"], name="risk_school_status_idx")]

    def clean(self):
        if self.student_id and self.student.school_id != self.school_id:
            raise ValidationError("Risk student must belong to its school.")
        if self.policy_id and self.policy.school_id != self.school_id:
            raise ValidationError("Risk policy must belong to its school.")


class Intervention(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    signal = models.ForeignKey(RiskSignal, on_delete=models.PROTECT, related_name="interventions")
    owner = models.ForeignKey("schools.SchoolMembership", on_delete=models.PROTECT, related_name="owned_interventions")
    plan = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    outcome = models.TextField(blank=True)
    created_by = models.ForeignKey("schools.SchoolMembership", on_delete=models.PROTECT, related_name="created_interventions")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        for field in ("owner", "created_by"):
            actor = getattr(self, field, None)
            if actor and actor.school_id != self.signal.school_id:
                raise ValidationError({field: "Intervention staff must belong to the signal school."})


class NarrativeSnapshot(models.Model):
    class Scope(models.TextChoices):
        SCHOOL = "SCHOOL", "School"
        CLASS = "CLASS", "Class"
        OFFERING = "OFFERING", "Subject offering"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        APPROVED = "APPROVED", "Approved"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="analytics_narratives")
    term = models.ForeignKey("academics.Term", on_delete=models.PROTECT, related_name="analytics_narratives")
    scope = models.CharField(max_length=10, choices=Scope.choices)
    school_class = models.ForeignKey(
        "academics.SchoolClass", null=True, blank=True, on_delete=models.PROTECT,
        related_name="analytics_narratives",
    )
    offering = models.ForeignKey(
        "academics.SubjectOffering", null=True, blank=True, on_delete=models.PROTECT,
        related_name="analytics_narratives",
    )
    metrics_snapshot = models.JSONField(default=dict)
    narrative = models.TextField()
    generation_method = models.CharField(max_length=40, default="grounded-template")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    generated_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="generated_analytics_narratives"
    )
    reviewed_by = models.ForeignKey(
        "schools.SchoolMembership", null=True, blank=True, on_delete=models.PROTECT,
        related_name="reviewed_analytics_narratives",
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        if self.term_id and self.term.academic_year.school_id != self.school_id:
            raise ValidationError("Narrative term must belong to its school.")
        if self.scope == self.Scope.CLASS and not self.school_class_id:
            raise ValidationError("Class narratives require a class.")
        if self.scope == self.Scope.OFFERING and not self.offering_id:
            raise ValidationError("Offering narratives require a subject offering.")

