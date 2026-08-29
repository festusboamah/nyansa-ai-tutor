from django.contrib import admin
from .models import (
    Answer,
    Assignment,
    AssignmentSubmission,
    Badge,
    BankQuestion,
    BankQuestionChoice,
    Choice,
    CriterionScore,
    ExamFeeWaiver,
    ExamIntegrityEvent,
    ExamSnapshot,
    Question,
    Quiz,
    RubricCriterion,
    Submission,
)


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 3  # shows 3 blank choice rows by default


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1
    show_change_link = True


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "teacher", "created_at")
    list_filter = ("subject",)
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "quiz", "question_type", "order")
    list_filter = ("question_type", "quiz", "topic")
    inlines = [ChoiceInline]


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("student", "quiz", "score", "submitted_at")
    list_filter = ("quiz",)


admin.site.register(Answer)
admin.site.register(ExamIntegrityEvent)
admin.site.register(ExamSnapshot)


@admin.register(ExamFeeWaiver)
class ExamFeeWaiverAdmin(admin.ModelAdmin):
    list_display = ("student", "quiz", "granted_by", "created_at")
    list_filter = ("quiz",)


class BankQuestionChoiceInline(admin.TabularInline):
    model = BankQuestionChoice
    extra = 3


@admin.register(BankQuestion)
class BankQuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "subject", "topic", "difficulty", "status", "created_by", "created_at")
    list_filter = ("status", "difficulty", "subject", "topic")
    inlines = [BankQuestionChoiceInline]


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("student", "badge_type", "submission", "awarded_at")
    list_filter = ("badge_type",)


class RubricCriterionInline(admin.TabularInline):
    model = RubricCriterion
    extra = 1


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "teacher", "deadline", "created_at")
    list_filter = ("subject",)
    inlines = [RubricCriterionInline]


class CriterionScoreInline(admin.TabularInline):
    model = CriterionScore
    extra = 0
    readonly_fields = ("criterion", "ai_score", "ai_feedback")
    can_delete = False


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("student", "assignment", "final_score", "max_score", "submitted_at")
    list_filter = ("assignment",)
    inlines = [CriterionScoreInline]