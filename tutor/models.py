from django.db import models
from django.conf import settings


class TutorMode(models.TextChoices):
    TEACH_ME = "TEACH_ME", "Teach Me"
    GUIDE_ME = "GUIDE_ME", "Guide Me"
    HINT = "HINT", "Give Me a Hint"
    PRACTICE = "PRACTICE", "Practice With Me"
    CHECK_MY_WORK = "CHECK_MY_WORK", "Check My Work"
    EXPLAIN_MY_MISTAKE = "EXPLAIN_MY_MISTAKE", "Explain My Mistake"
    REVISE_WITH_ME = "REVISE_WITH_ME", "Revise With Me"
    EXAM_MODE = "EXAM_MODE", "Exam Mode"


class TutorSession(models.Model):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="tutor_sessions"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tutor_sessions"
    )
    mode = models.CharField(max_length=20, choices=TutorMode.choices)
    subject = models.ForeignKey(
        "courses.Subject", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tutor_sessions",
    )
    study_document = models.ForeignKey(
        "courses.StudyDocument", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tutor_sessions",
    )
    material = models.ForeignKey(
        "courses.Material", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tutor_sessions",
    )
    topic = models.ForeignKey(
        "mastery.Topic", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tutor_sessions",
    )
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["school", "student"], name="tutor_session_school_idx")]
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title or f"{self.get_mode_display()} ({self.student.username})"


class TutorMessageRole(models.TextChoices):
    STUDENT = "STUDENT", "Student"
    TUTOR = "TUTOR", "Tutor"


class TutorMessage(models.Model):
    session = models.ForeignKey(
        TutorSession, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=TutorMessageRole.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


DEFAULT_MAX_HINT_DEPTH = 4


class DifficultyLevel(models.TextChoices):
    EASY = "easy", "Easy"
    MEDIUM = "medium", "Medium"
    HARD = "hard", "Hard"


DIFFICULTY_ORDER = [DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD]


class TutorSettings(models.Model):
    school = models.OneToOneField(
        "schools.School", on_delete=models.CASCADE, related_name="tutor_settings"
    )
    disabled_modes = models.JSONField(default=list, blank=True)
    max_hint_depth = models.PositiveIntegerField(default=DEFAULT_MAX_HINT_DEPTH)
    allow_final_answer_reveal = models.BooleanField(default=False)
    daily_usage_limit = models.PositiveIntegerField(null=True, blank=True)
    min_difficulty = models.CharField(
        max_length=10, choices=DifficultyLevel.choices, default=DifficultyLevel.EASY
    )
    max_difficulty = models.CharField(
        max_length=10, choices=DifficultyLevel.choices, default=DifficultyLevel.HARD
    )
    restricted_period_start = models.DateField(null=True, blank=True)
    restricted_period_end = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Tutor settings ({self.school.name})"


class TutorUsageEvent(models.Model):
    session = models.ForeignKey(
        TutorSession, on_delete=models.CASCADE, related_name="usage_events"
    )
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
        return f"{self.model} ({status}) - session {self.session_id}"
