from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class GradeScheme(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="grade_schemes")
    academic_year = models.ForeignKey(
        "academics.AcademicYear", on_delete=models.CASCADE, related_name="grade_schemes"
    )
    name = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-academic_year__start_date", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "academic_year", "name"], name="unique_grade_scheme_name_per_year"
            )
        ]

    def clean(self):
        if self.academic_year_id and self.school_id != self.academic_year.school_id:
            raise ValidationError("Grade scheme and academic year must belong to the same school.")

    def __str__(self):
        return f"{self.name} ({self.academic_year.name})"


class AssessmentCategory(models.Model):
    scheme = models.ForeignKey(GradeScheme, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=30)
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Percentage contribution to the final result.",
    )
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["scheme", "code"], name="unique_category_code_per_scheme"),
            models.UniqueConstraint(fields=["scheme", "order"], name="unique_category_order_per_scheme"),
        ]

    def clean(self):
        if self.weight is not None and self.weight > Decimal("100.00"):
            raise ValidationError({"weight": "Category weight cannot exceed 100%."})

    def __str__(self):
        return f"{self.name} ({self.weight}%)"


class Assessment(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        CLOSED = "CLOSED", "Closed"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="assessments")
    offering = models.ForeignKey(
        "academics.SubjectOffering", on_delete=models.CASCADE, related_name="assessments"
    )
    category = models.ForeignKey(
        AssessmentCategory, on_delete=models.PROTECT, related_name="assessments"
    )
    title = models.CharField(max_length=150)
    max_score = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    due_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["offering_id", "due_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["offering", "category", "title"], name="unique_assessment_title_per_category"
            )
        ]

    def clean(self):
        errors = {}
        if self.offering_id and self.school_id != self.offering.school_id:
            errors["offering"] = "Assessment and subject offering must belong to the same school."
        if self.category_id:
            scheme = self.category.scheme
            if self.school_id != scheme.school_id:
                errors["category"] = "Assessment category must belong to the same school."
            elif self.offering_id and scheme.academic_year_id != self.offering.term.academic_year_id:
                errors["category"] = "Assessment category must belong to the offering's academic year."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.title


class GradeEntry(models.Model):
    class Source(models.TextChoices):
        ONLINE = "ONLINE", "Online activity"
        MANUAL = "MANUAL", "Manual entry"
        IMPORT = "IMPORT", "Spreadsheet import"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="grade_entries")
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="grade_entries")
    student = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.CASCADE, related_name="grade_entries"
    )
    recorded_by = models.ForeignKey(
        "schools.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="recorded_grade_entries",
    )
    score = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["assessment_id", "student_id"]
        constraints = [
            models.UniqueConstraint(fields=["assessment", "student"], name="unique_student_assessment_grade")
        ]
        indexes = [models.Index(fields=["school", "student", "status"], name="grade_school_student_idx")]

    def clean(self):
        from academics.models import ClassEnrollment
        from schools.models import SchoolMembership

        errors = {}
        if self.assessment_id and self.school_id != self.assessment.school_id:
            errors["assessment"] = "Grade entry and assessment must belong to the same school."
        if self.student_id and (
            self.student.school_id != self.school_id or self.student.role != SchoolMembership.Role.STUDENT
        ):
            errors["student"] = "Student must have a student membership in the same school."
        elif self.student_id and self.student.status != SchoolMembership.Status.ACTIVE:
            errors["student"] = "Student membership must be active."
        if self.recorded_by_id and (
            self.recorded_by.school_id != self.school_id
            or self.recorded_by.role not in {SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN}
        ):
            errors["recorded_by"] = "Recorder must be a teacher or administrator in the same school."
        if self.assessment_id and self.score is not None and self.score > self.assessment.max_score:
            errors["score"] = "Score cannot exceed the assessment maximum."
        if self.assessment_id and self.student_id and self.student.school_id == self.school_id:
            enrolled = ClassEnrollment.objects.filter(
                school_class=self.assessment.offering.school_class,
                student=self.student,
                status=ClassEnrollment.Status.ACTIVE,
            ).exists()
            if not enrolled:
                errors["student"] = "Student must be actively enrolled in the assessment class."
        if errors:
            raise ValidationError(errors)

    @property
    def percentage(self):
        if not self.assessment_id or not self.assessment.max_score:
            return None
        return (self.score / self.assessment.max_score * Decimal("100")).quantize(Decimal("0.01"))


class GradeImportBatch(models.Model):
    class Status(models.TextChoices):
        PREVIEW = "PREVIEW", "Awaiting confirmation"
        CONFIRMED = "CONFIRMED", "Confirmed"
        CANCELLED = "CANCELLED", "Cancelled"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="grade_import_batches")
    assessment = models.ForeignKey(Assessment, on_delete=models.PROTECT, related_name="import_batches")
    uploaded_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="uploaded_grade_imports"
    )
    confirmed_by = models.ForeignKey(
        "schools.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="confirmed_grade_imports",
    )
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PREVIEW)
    row_count = models.PositiveIntegerField(default=0)
    valid_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [models.Index(fields=["school", "status", "uploaded_at"], name="import_school_status_idx")]

    def clean(self):
        from schools.models import SchoolMembership

        errors = {}
        if self.assessment_id and self.assessment.school_id != self.school_id:
            errors["assessment"] = "Import batch and assessment must belong to the same school."
        for field in ("uploaded_by", "confirmed_by"):
            membership = getattr(self, field, None)
            if membership and (
                membership.school_id != self.school_id
                or membership.role not in {SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN}
            ):
                errors[field] = "Import operator must be a teacher or administrator in the same school."
        if errors:
            raise ValidationError(errors)


class GradeImportRow(models.Model):
    class Status(models.TextChoices):
        VALID = "VALID", "Ready"
        ERROR = "ERROR", "Error"
        SKIPPED = "SKIPPED", "Blank score"
        IMPORTED = "IMPORTED", "Imported"

    batch = models.ForeignKey(GradeImportBatch, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    student = models.ForeignKey(
        "schools.SchoolMembership", null=True, blank=True, on_delete=models.PROTECT, related_name="grade_import_rows"
    )
    raw_student_id = models.CharField(max_length=100, blank=True)
    raw_score = models.CharField(max_length=100, blank=True)
    score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["row_number"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "row_number"], name="unique_import_batch_row"),
            models.UniqueConstraint(
                fields=["batch", "student"],
                condition=models.Q(student__isnull=False),
                name="unique_import_batch_student",
            ),
        ]
