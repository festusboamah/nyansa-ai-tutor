from django.db import models
from django.conf import settings
from courses.models import Subject


class LessonNote(models.Model):
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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.subject.name} - {self.strand_topic} ({self.week_ending})"