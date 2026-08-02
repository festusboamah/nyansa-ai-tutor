from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class AcademicYear(models.Model):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="academic_years")
    name = models.CharField(max_length=30)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_school_academic_year"),
            models.UniqueConstraint(fields=["school"], condition=Q(is_current=True), name="one_current_year_per_school"),
        ]

    def clean(self):
        if self.end_date <= self.start_date:
            raise ValidationError({"end_date": "End date must be after start date."})

    def __str__(self):
        return f"{self.school}: {self.name}"


class Term(models.Model):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="terms")
    name = models.CharField(max_length=40)
    order = models.PositiveSmallIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["academic_year", "order"]
        constraints = [
            models.UniqueConstraint(fields=["academic_year", "name"], name="unique_term_name_per_year"),
            models.UniqueConstraint(fields=["academic_year", "order"], name="unique_term_order_per_year"),
        ]

    def clean(self):
        errors = {}
        if self.end_date <= self.start_date:
            errors["end_date"] = "End date must be after start date."
        if self.academic_year_id and (self.start_date < self.academic_year.start_date or self.end_date > self.academic_year.end_date):
            errors["start_date"] = "Term dates must fall within the academic year."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.academic_year.name} - {self.name}"


class SchoolClass(models.Model):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="classes")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="classes")
    name = models.CharField(max_length=80)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    class_teacher = models.ForeignKey("schools.SchoolMembership", null=True, blank=True, on_delete=models.SET_NULL, related_name="managed_classes")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["school", "academic_year", "name"], name="unique_class_per_year")]

    def clean(self):
        if self.academic_year_id and self.school_id != self.academic_year.school_id:
            raise ValidationError("Class and academic year must belong to the same school.")
        if self.class_teacher_id and (
            self.class_teacher.school_id != self.school_id
            or self.class_teacher.role != "TEACHER"
        ):
            raise ValidationError("Class teacher must be a teacher in the same school.")

    def __str__(self):
        return f"{self.name} ({self.academic_year.name})"


class ClassEnrollment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        TRANSFERRED = "TRANSFERRED", "Transferred"
        COMPLETED = "COMPLETED", "Completed"

    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="student_enrollments")
    student = models.ForeignKey("schools.SchoolMembership", on_delete=models.CASCADE, related_name="class_enrollments")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    enrolled_on = models.DateField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school_class", "student"], name="unique_student_class_enrollment")]

    def clean(self):
        if self.school_class_id and self.student_id and (
            self.student.school_id != self.school_class.school_id
            or self.student.role != "STUDENT"
        ):
            raise ValidationError("Student must have a student membership in the class school.")


class SubjectOffering(models.Model):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="subject_offerings")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="subject_offerings")
    subject = models.ForeignKey("courses.Subject", on_delete=models.CASCADE, related_name="offerings")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="subject_offerings")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school_class", "subject", "term"], name="unique_subject_offering")]

    def clean(self):
        school_ids = {self.school_id, self.school_class.school_id, self.subject.school_id, self.term.academic_year.school_id}
        if len(school_ids) != 1:
            raise ValidationError("All offering records must belong to the same school.")

    def __str__(self):
        return f"{self.school_class.name} — {self.subject.name} — {self.term.name}"


class TeacherAssignment(models.Model):
    offering = models.ForeignKey(SubjectOffering, on_delete=models.CASCADE, related_name="teacher_assignments")
    teacher = models.ForeignKey("schools.SchoolMembership", on_delete=models.CASCADE, related_name="teaching_assignments")
    is_lead = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["offering", "teacher"], name="unique_teacher_offering")]

    def clean(self):
        if self.offering_id and (
            self.teacher.school_id != self.offering.school_id
            or self.teacher.role != "TEACHER"
        ):
            raise ValidationError("Teacher must have a teacher membership in the offering school.")

    def __str__(self):
        return f"{self.teacher.user.get_full_name() or self.teacher.user.username} — {self.offering}"
