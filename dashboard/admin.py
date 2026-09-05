from django.contrib import admin
from .models import (
    LessonNote, LessonNoteEvent, LessonNoteNotification, LessonNoteVersion,
    SchemeOfLearning, StudentNote,
)


@admin.register(LessonNote)
class LessonNoteAdmin(admin.ModelAdmin):
    list_display = ("subject", "strand_topic", "class_level", "week_ending", "teacher", "status", "current_version")
    list_filter = ("status", "subject", "class_level")


@admin.register(LessonNoteVersion)
class LessonNoteVersionAdmin(admin.ModelAdmin):
    list_display = ("lesson_note", "version_number", "created_by", "created_at")
    readonly_fields = ("lesson_note", "version_number", "snapshot", "reason", "created_by", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LessonNoteEvent)
class LessonNoteEventAdmin(admin.ModelAdmin):
    list_display = ("lesson_note", "event_type", "actor", "created_at")
    readonly_fields = ("lesson_note", "event_type", "message", "actor", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LessonNoteNotification)
class LessonNoteNotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "lesson_note", "created_at", "read_at")
    readonly_fields = ("recipient", "lesson_note", "message", "created_at", "read_at")


@admin.register(SchemeOfLearning)
class SchemeOfLearningAdmin(admin.ModelAdmin):
    list_display = ("subject", "class_level", "term", "num_weeks", "teacher", "created_at")
    list_filter = ("subject", "class_level")


@admin.register(StudentNote)
class StudentNoteAdmin(admin.ModelAdmin):
    list_display = ("subject", "topic", "class_level", "teacher", "created_at")
    list_filter = ("subject", "class_level")
