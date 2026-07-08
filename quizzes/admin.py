from django.contrib import admin
from .models import Quiz, Question, Choice, Submission, Answer, Badge


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
    list_filter = ("question_type", "quiz")
    inlines = [ChoiceInline]


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("student", "quiz", "score", "submitted_at")
    list_filter = ("quiz",)


admin.site.register(Answer)


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("student", "badge_type", "submission", "awarded_at")
    list_filter = ("badge_type",)