from django.db import models
from django.conf import settings
from courses.models import Subject


class Quiz(models.Model):
    class AssessmentType(models.TextChoices):
        QUIZ = "QUIZ", "Quiz"
        EXAM = "EXAM", "Exam"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

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
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PUBLISHED)
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
    topic = models.ForeignKey(
        "mastery.Topic", null=True, blank=True, on_delete=models.SET_NULL, related_name="questions"
    )

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
    deadline = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def is_past_deadline(self):
        if self.deadline is None:
            return False
        from django.utils import timezone
        return timezone.now() > self.deadline


class RubricCriterion(models.Model):
    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="criteria"
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, help_text="What does 'good' look like for this criterion?")
    max_points = models.FloatField(default=10)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


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


class CriterionScore(models.Model):
    submission = models.ForeignKey(
        AssignmentSubmission, on_delete=models.CASCADE, related_name="criterion_scores"
    )
    criterion = models.ForeignKey(RubricCriterion, on_delete=models.CASCADE)
    ai_score = models.FloatField(null=True, blank=True)
    ai_feedback = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["submission", "criterion"], name="unique_submission_criterion")
        ]

    def __str__(self):
        return f"{self.criterion.name} - {self.submission}"


class BankQuestion(models.Model):
    class Difficulty(models.TextChoices):
        EASY = "easy", "Easy"
        MEDIUM = "medium", "Medium"
        HARD = "hard", "Hard"

    class Status(models.TextChoices):
        PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="bank_questions"
    )
    topic = models.ForeignKey(
        "mastery.Topic", null=True, blank=True, on_delete=models.SET_NULL, related_name="bank_questions"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bank_questions"
    )
    text = models.TextField()
    question_type = models.CharField(
        max_length=10, choices=Question.QuestionType.choices, default=Question.QuestionType.MULTIPLE_CHOICE
    )
    difficulty = models.CharField(max_length=10, choices=Difficulty.choices, default=Difficulty.MEDIUM)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING_REVIEW)
    reviewed_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_bank_questions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.text[:50]


class BankQuestionChoice(models.Model):
    question = models.ForeignKey(
        BankQuestion, on_delete=models.CASCADE, related_name="choices"
    )
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class QuizGenerationSettings(models.Model):
    school = models.OneToOneField(
        "schools.School", on_delete=models.CASCADE, related_name="quiz_generation_settings"
    )
    require_review = models.BooleanField(default=True)

    def __str__(self):
        return f"Quiz generation settings ({self.school.name})"