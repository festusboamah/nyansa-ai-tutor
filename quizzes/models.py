from decimal import Decimal

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from courses.models import Subject


class Quiz(models.Model):
    class AssessmentType(models.TextChoices):
        QUIZ = "QUIZ", "Quiz"
        EXAM = "EXAM", "Exam"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    class ResultsReleaseMode(models.TextChoices):
        INSTANT = "INSTANT", "Instant"
        SCHEDULED = "SCHEDULED", "Scheduled"
        MANUAL = "MANUAL", "Manual publish"

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
    starts_at = models.DateTimeField(
        null=True, blank=True,
        help_text="For exams: when this exam window opens. Leave blank for quizzes without a fixed start.",
    )
    essay_weight_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Essay questions' share of the combined score (0-100). The rest is the objective share.",
    )
    results_release_mode = models.CharField(
        max_length=10, choices=ResultsReleaseMode.choices, default=ResultsReleaseMode.INSTANT, blank=True,
    )
    results_release_at = models.DateTimeField(
        null=True, blank=True, help_text="Required when results release mode is Scheduled.",
    )
    results_published_at = models.DateTimeField(
        null=True, blank=True, help_text="Set once results are actually released to students.",
    )
    require_webcam_snapshots = models.BooleanField(default=False, blank=True)
    snapshot_interval_seconds = models.PositiveIntegerField(default=90, blank=True)
    offerings = models.ManyToManyField(
        "academics.SubjectOffering", blank=True, related_name="quizzes",
        help_text="For exams: the class/subject offerings sitting this exam. Leave empty for a subject-wide quiz.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def clean(self):
        errors = {}
        if self.essay_weight_percent is not None and not (Decimal("0") <= self.essay_weight_percent <= Decimal("100")):
            errors["essay_weight_percent"] = "Essay weight must be between 0 and 100."
        if self.results_release_mode == self.ResultsReleaseMode.SCHEDULED and not self.results_release_at:
            errors["results_release_at"] = "A release time is required for scheduled release."
        if self.starts_at and self.deadline and self.starts_at >= self.deadline:
            errors["starts_at"] = "The exam must start before its deadline."
        if errors:
            raise ValidationError(errors)

    @property
    def objective_weight_percent(self):
        if self.essay_weight_percent is None:
            return Decimal("100")
        return Decimal("100") - self.essay_weight_percent

    def is_before_start(self):
        if self.starts_at is None:
            return False
        return timezone.now() < self.starts_at

    def is_past_deadline(self):
        if self.deadline is None:
            return False
        return timezone.now() > self.deadline

    def results_are_visible(self):
        if self.assessment_type != self.AssessmentType.EXAM:
            return True
        if self.results_release_mode == self.ResultsReleaseMode.INSTANT:
            return True
        return self.results_published_at is not None


class Question(models.Model):
    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = "MCQ", "Multiple Choice"
        SHORT_ANSWER = "SHORT", "Short Answer"
        ESSAY = "ESSAY", "Essay / Subjective"

    quiz = models.ForeignKey(
        Quiz, on_delete=models.CASCADE, related_name="questions"
    )
    text = models.TextField()
    question_type = models.CharField(
        max_length=10, choices=QuestionType.choices, default=QuestionType.MULTIPLE_CHOICE
    )
    points = models.FloatField(default=1.0, help_text="Max marks for this question.")
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
    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(
        default=timezone.now, null=True, blank=True,
        help_text="Null while an exam attempt is still in progress.",
    )
    expires_at = models.DateTimeField(
        null=True, blank=True,
        help_text="For exams: the server-side cutoff for this attempt (start + time limit, capped at the exam deadline).",
    )
    score = models.FloatField(null=True, blank=True)
    ai_feedback = models.TextField(blank=True)
    camera_consent_given = models.BooleanField(default=False)
    camera_consent_at = models.DateTimeField(null=True, blank=True)
    flagged_for_review = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.student.username} - {self.quiz.title}"

    def is_expired(self):
        return self.expires_at is not None and timezone.now() > self.expires_at

    def is_finished(self):
        return self.submitted_at is not None


class Answer(models.Model):
    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(
        Choice, on_delete=models.SET_NULL, null=True, blank=True
    )
    text_answer = models.TextField(blank=True)
    file_answer = models.FileField(upload_to="exam_essay_answers/%Y/%m/", null=True, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    ai_feedback = models.TextField(blank=True)

    # Essay grading: AI suggests, a teacher confirms. AI never writes to points_awarded.
    ai_suggested_points = models.FloatField(null=True, blank=True)
    ai_suggested_feedback = models.TextField(blank=True)
    points_awarded = models.FloatField(null=True, blank=True)
    teacher_feedback = models.TextField(blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Answer to: {self.question.text[:30]}"

    def is_graded(self):
        if self.question.question_type == Question.QuestionType.ESSAY:
            return self.points_awarded is not None
        return True


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


class ExamIntegrityEvent(models.Model):
    class EventType(models.TextChoices):
        TAB_HIDDEN = "TAB_HIDDEN", "Tab hidden"
        BLUR = "BLUR", "Window lost focus"
        FULLSCREEN_EXIT = "FULLSCREEN_EXIT", "Exited fullscreen"
        CAMERA_DENIED = "CAMERA_DENIED", "Camera permission denied"
        CAMERA_ERROR = "CAMERA_ERROR", "Camera error"

    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE, related_name="integrity_events"
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    occurred_at = models.DateTimeField(auto_now_add=True)
    detail = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["occurred_at"]

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.submission}"


class ExamSnapshot(models.Model):
    class Trigger(models.TextChoices):
        INTERVAL = "INTERVAL", "Periodic interval"
        TAB_SWITCH = "TAB_SWITCH", "Tab switch"
        BLUR = "BLUR", "Window blur"
        ATTEMPT_START = "ATTEMPT_START", "Attempt start"

    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE, related_name="snapshots"
    )
    image = models.FileField(upload_to="exam_snapshots/%Y/%m/%d/")
    captured_at = models.DateTimeField(auto_now_add=True)
    trigger = models.CharField(max_length=20, choices=Trigger.choices, default=Trigger.INTERVAL)

    class Meta:
        ordering = ["captured_at"]

    def __str__(self):
        return f"Snapshot for {self.submission} at {self.captured_at}"


class ExamFeeWaiver(models.Model):
    student = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.CASCADE, related_name="exam_fee_waivers"
    )
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="fee_waivers")
    granted_by = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="granted_exam_fee_waivers"
    )
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "quiz"], name="unique_exam_fee_waiver_per_student")
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Exam fee waivers are immutable; revoke by deleting and re-granting if needed.")
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Fee waiver: {self.student} for {self.quiz}"