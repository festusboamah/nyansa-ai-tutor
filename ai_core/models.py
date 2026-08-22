from django.db import models

from schools.models import School


class AIUsageEvent(models.Model):
    class Source(models.TextChoices):
        STUDY_AI = "study_ai", "Self-Study Hub"
        QUIZ_GENERATION = "quiz_generation", "Quiz Generation"
        QUIZ_GRADING = "quiz_grading", "Quiz Grading"
        ASSIGNMENT_GRADING = "assignment_grading", "Assignment Grading"
        LESSON_AI = "lesson_ai", "Lesson Notes"
        STUDENT_REPORTS = "student_reports", "Student Reports"
        ANALYTICS_NARRATIVE = "analytics_narrative", "Analytics Narratives"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="ai_usage_events")
    source = models.CharField(max_length=30, choices=Source.choices)
    model = models.CharField(max_length=100)
    input_tokens = models.IntegerField(null=True, blank=True)
    output_tokens = models.IntegerField(null=True, blank=True)
    succeeded = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        status = "ok" if self.succeeded else "failed"
        return f"{self.source} ({status}) - {self.school_id}"
