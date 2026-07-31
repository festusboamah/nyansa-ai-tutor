from django.core.exceptions import ValidationError
from django.db import models


class SchoolCalendarPolicy(models.Model):
    school = models.OneToOneField(
        "schools.School", on_delete=models.CASCADE, related_name="calendar_policy"
    )
    instructional_weekdays = models.CharField(
        max_length=20,
        default="0,1,2,3,4",
        help_text="Comma-separated weekday numbers where Monday is 0 and Sunday is 6.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        try:
            values = [int(value.strip()) for value in self.instructional_weekdays.split(",") if value.strip()]
        except ValueError as error:
            raise ValidationError({"instructional_weekdays": "Use weekday numbers from 0 to 6."}) from error
        if not values or len(values) != len(set(values)) or any(value < 0 or value > 6 for value in values):
            raise ValidationError({"instructional_weekdays": "Choose unique weekday numbers from 0 to 6."})

    @property
    def weekday_set(self):
        return {int(value.strip()) for value in self.instructional_weekdays.split(",") if value.strip()}


class SchoolClosure(models.Model):
    class ClosureType(models.TextChoices):
        HOLIDAY = "HOLIDAY", "Holiday"
        CLOSURE = "CLOSURE", "School closure"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="closures")
    term = models.ForeignKey("academics.Term", on_delete=models.CASCADE, related_name="closures")
    name = models.CharField(max_length=120)
    closure_type = models.CharField(max_length=10, choices=ClosureType.choices, default=ClosureType.HOLIDAY)
    start_date = models.DateField()
    end_date = models.DateField()
    created_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="created_school_closures"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_date", "id"]

    def clean(self):
        errors = {}
        if self.end_date < self.start_date:
            errors["end_date"] = "End date cannot be before start date."
        if self.term_id:
            if self.term.academic_year.school_id != self.school_id:
                errors["term"] = "Closure term must belong to the same school."
            elif self.start_date < self.term.start_date or self.end_date > self.term.end_date:
                errors["start_date"] = "Closure dates must fall within the term."
        if self.created_by_id and (
            self.created_by.school_id != self.school_id or self.created_by.role != "SCHOOL_ADMIN"
        ):
            errors["created_by"] = "Closure creator must be an administrator in the same school."
        if errors:
            raise ValidationError(errors)


class AttendanceSession(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="attendance_sessions")
    school_class = models.ForeignKey(
        "academics.SchoolClass", on_delete=models.CASCADE, related_name="attendance_sessions"
    )
    term = models.ForeignKey("academics.Term", on_delete=models.CASCADE, related_name="attendance_sessions")
    attendance_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    submitted_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="submitted_attendance_sessions"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-attendance_date"]
        constraints = [
            models.UniqueConstraint(fields=["school_class", "attendance_date"], name="unique_class_attendance_date")
        ]

    def clean(self):
        errors = {}
        if self.school_class_id and self.school_class.school_id != self.school_id:
            errors["school_class"] = "Attendance class must belong to the same school."
        if self.term_id:
            if self.term.academic_year.school_id != self.school_id:
                errors["term"] = "Attendance term must belong to the same school."
            elif not self.term.start_date <= self.attendance_date <= self.term.end_date:
                errors["attendance_date"] = "Attendance date must fall within the term."
        if self.school_class_id and self.term_id and self.school_class.academic_year_id != self.term.academic_year_id:
            errors["term"] = "Class and term must belong to the same academic year."
        if self.submitted_by_id and self.submitted_by.school_id != self.school_id:
            errors["submitted_by"] = "Attendance recorder must belong to the same school."
        if errors:
            raise ValidationError(errors)


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", "Present"
        ABSENT = "ABSENT", "Absent"
        EXCUSED = "EXCUSED", "Excused"

    session = models.ForeignKey(AttendanceSession, on_delete=models.PROTECT, related_name="records")
    student = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="attendance_records"
    )
    status = models.CharField(max_length=10, choices=Status.choices)
    marked_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="marked_attendance_records"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["student_id"]
        constraints = [
            models.UniqueConstraint(fields=["session", "student"], name="unique_student_attendance_session")
        ]

    def clean(self):
        from academics.models import ClassEnrollment

        errors = {}
        if self.student_id and (
            self.student.school_id != self.session.school_id or self.student.role != "STUDENT"
        ):
            errors["student"] = "Student must belong to the attendance school."
        elif self.student_id and not ClassEnrollment.objects.filter(
            school_class=self.session.school_class, student=self.student
        ).exists():
            errors["student"] = "Student must be enrolled in the attendance class."
        if self.marked_by_id and self.marked_by.school_id != self.session.school_id:
            errors["marked_by"] = "Attendance marker must belong to the same school."
        if errors:
            raise ValidationError(errors)


class AttendanceRevision(models.Model):
    record = models.ForeignKey(AttendanceRecord, on_delete=models.PROTECT, related_name="revisions")
    previous_status = models.CharField(max_length=10, choices=AttendanceRecord.Status.choices)
    new_status = models.CharField(max_length=10, choices=AttendanceRecord.Status.choices)
    reason = models.CharField(max_length=500)
    changed_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="attendance_revisions"
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at", "-id"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Attendance correction history is immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Attendance correction history is immutable.")
