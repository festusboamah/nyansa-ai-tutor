from django.db import models
from django.conf import settings
from courses.models import Subject


class Quiz(models.Model):
    class AssessmentType(models.TextChoices):
        QUIZ = "QUIZ", "Quiz"
        EXAM = "EXAM", "Exam"

    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="quizzes"
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quizzes"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    assessment_type = models.CharField(
        max_length=10, choices=AssessmentType.choices, default=AssessmentType.QUIZ
    )
    time_limit_minutes = models.PositiveIntegerField(
        default=15, help_text="Time limit for students to complete this quiz, in minutes"
    )
    max_attempts = models.PositiveIntegerField(
        default=2, help_text="Maximum number of attempts a student can make"
    )
    deadline = models.DateTimeField(
        null=True, blank=True, help_text="Optional deadline after which students cannot submit"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def is_past_deadline(self):
        if self.deadline is None:
            return False
        from django.utils import timezone
        return timezone.now() > self.deadline


class Question(models.Model):
    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = "MCQ", "Multiple Choice"
        SHORT_ANSWER = "SHORT", "Short Answer"

    quiz = models.ForeignKey(
        Quiz, on_delete=models.CASCADE, related_name="questions"
    )
    text = models.TextField()
    question_type = models.CharField(
        max_length=10, choices=QuestionType.choices, default=QuestionType.MULTIPLE_CHOICE
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.text[:50]


class Choice(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="choices"
    )
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class Submission(models.Model):
    quiz = models.ForeignKey(
        Quiz, on_delete=models.CASCADE, related_name="submissions"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions"
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    score = models.FloatField(null=True, blank=True)
    ai_feedback = models.TextField(blank=True)

    def __str__(self):
        return f"{self.student.username} - {self.quiz.title}"


class Answer(models.Model):
    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(
        Choice, on_delete=models.SET_NULL, null=True, blank=True
    )
    text_answer = models.TextField(blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    ai_feedback = models.TextField(blank=True)

    def __str__(self):
        return f"Answer to: {self.question.text[:30]}"


class Badge(models.Model):
    class BadgeType(models.TextChoices):
        PERFECT_SCORE = "PERFECT", "Perfect Score"
        FIRST_ATTEMPT = "FIRST", "First Try Success"
        IMPROVED = "IMPROVED", "Most Improved"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="badges"
    )
    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE, related_name="badges"
    )
    badge_type = models.CharField(max_length=10, choices=BadgeType.choices)
    awarded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.username} - {self.get_badge_type_display()}"


class Assignment(models.Model):
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="assignments"
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assignments"
    )
    title = models.CharField(max_length=200)
    instructions = models.TextField(blank=True)
    grading_rubric = models.TextField(
        blank=True, help_text="Optional: describe how this should be graded, for AI reference"
    )
    deadline = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def is_past_deadline(self):
        if self.deadline is None:
            return False
        from django.utils import timezone
        return timezone.now() > self.deadline


class AssignmentSubmission(models.Model):
    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="submissions"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assignment_submissions"
    )
    file = models.FileField(upload_to="assignment_submissions/")
    submitted_at = models.DateTimeField(auto_now_add=True)

    ai_suggested_score = models.FloatField(null=True, blank=True)
    ai_suggested_feedback = models.TextField(blank=True)

    final_score = models.FloatField(null=True, blank=True)
    max_score = models.FloatField(default=100)
    teacher_feedback = models.TextField(blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.student.username} - {self.assignment.title}"

    def is_graded(self):
        return self.final_score is not None