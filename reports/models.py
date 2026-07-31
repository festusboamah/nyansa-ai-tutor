from django.core.exceptions import ValidationError
from django.db import models


class ReportPolicy(models.Model):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="report_policies")
    academic_year = models.OneToOneField(
        "academics.AcademicYear", on_delete=models.CASCADE, related_name="report_policy"
    )
    show_position = models.BooleanField(default=False)
    pass_mark = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    promotion_average = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.academic_year_id and self.school_id != self.academic_year.school_id:
            raise ValidationError("Report policy and academic year must belong to the same school.")
        for field in ("pass_mark", "promotion_average"):
            value = getattr(self, field)
            if value < 0 or value > 100:
                raise ValidationError({field: "Enter a value from 0 to 100."})


class TermReport(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING = "PENDING", "Pending review"
        RETURNED = "RETURNED", "Sent back"
        APPROVED = "APPROVED", "Approved"
        PUBLISHED = "PUBLISHED", "Published"

    class Promotion(models.TextChoices):
        PROMOTED = "PROMOTED", "Promoted"
        REPEATED = "REPEATED", "Repeated"
        PENDING = "PENDING", "Pending decision"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="term_reports")
    school_class = models.ForeignKey(
        "academics.SchoolClass", on_delete=models.PROTECT, related_name="term_reports"
    )
    term = models.ForeignKey("academics.Term", on_delete=models.PROTECT, related_name="term_reports")
    student = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="term_reports"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=1)
    snapshot = models.JSONField(default=dict)
    total_score = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    average_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    position = models.PositiveIntegerField(null=True, blank=True)
    conduct = models.CharField(max_length=120, blank=True)
    teacher_remark = models.TextField(blank=True)
    administrator_remark = models.TextField(blank=True)
    promotion_outcome = models.CharField(
        max_length=10, choices=Promotion.choices, default=Promotion.PENDING
    )
    prepared_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="prepared_term_reports"
    )
    reviewed_by = models.ForeignKey(
        "schools.SchoolMembership", null=True, blank=True, on_delete=models.PROTECT,
        related_name="reviewed_term_reports"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school_class__name", "student__user__last_name", "student_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["school_class", "term", "student"], name="unique_student_term_report"
            )
        ]
        indexes = [models.Index(fields=["school", "term", "status"], name="report_school_term_idx")]

    def clean(self):
        errors = {}
        if self.school_class_id and self.school_class.school_id != self.school_id:
            errors["school_class"] = "Class must belong to the report school."
        if self.term_id and self.term.academic_year.school_id != self.school_id:
            errors["term"] = "Term must belong to the report school."
        if self.school_class_id and self.term_id and self.school_class.academic_year_id != self.term.academic_year_id:
            errors["term"] = "Term and class must belong to the same academic year."
        if self.student_id and (self.student.school_id != self.school_id or self.student.role != "STUDENT"):
            errors["student"] = "Student must belong to the report school."
        if errors:
            raise ValidationError(errors)


class ReportWorkflowEvent(models.Model):
    class Action(models.TextChoices):
        GENERATED = "GENERATED", "Generated"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        RETURNED = "RETURNED", "Returned"
        PUBLISHED = "PUBLISHED", "Published"
        REOPENED = "REOPENED", "Reopened"

    report = models.ForeignKey(TermReport, on_delete=models.PROTECT, related_name="workflow_events")
    action = models.CharField(max_length=10, choices=Action.choices)
    from_status = models.CharField(max_length=10, choices=TermReport.Status.choices, blank=True)
    to_status = models.CharField(max_length=10, choices=TermReport.Status.choices)
    note = models.CharField(max_length=500, blank=True)
    actor = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="report_workflow_events"
    )
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Report workflow history is immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Report workflow history is immutable.")

