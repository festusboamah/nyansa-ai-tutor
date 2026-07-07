from django.db import models
from django.conf import settings


class Subject(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

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

    def __str__(self):
        return f"{self.title} ({self.subject.name})"