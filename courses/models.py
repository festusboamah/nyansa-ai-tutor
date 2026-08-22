from django.db import models
from django.conf import settings


class Subject(models.Model):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="subjects"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["school", "name"], name="subject_school_name_idx")]

    def __str__(self):
        return self.name


class Material(models.Model):
    class MaterialType(models.TextChoices):
        DOCUMENT = "DOCUMENT", "Document"
        VIDEO = "VIDEO", "Video"

    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="materials"
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="materials"
    )
    title = models.CharField(max_length=200)
    material_type = models.CharField(max_length=10, choices=MaterialType.choices)
    file = models.FileField(upload_to="materials/", blank=True, null=True)
    video_url = models.URLField(blank=True, help_text="Use this for YouTube/Vimeo links")
    description = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    extracted_text = models.TextField(blank=True)

    def __str__(self):
        return f"{self.title} ({self.subject.name})"


class Enrollment(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="enrollments"
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "subject")

    def __str__(self):
        return f"{self.student.username} → {self.subject.name}"


class StudyDocument(models.Model):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="study_documents"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="study_documents"
    )
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="study_documents/")
    extracted_text = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.student.username})"


class StudyQuestion(models.Model):
    document = models.ForeignKey(
        StudyDocument, on_delete=models.CASCADE, related_name="questions"
    )
    question = models.TextField()
    answer = models.TextField(blank=True)
    asked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question[:50]
