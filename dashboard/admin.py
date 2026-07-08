from django.contrib import admin
from .models import LessonNote


@admin.register(LessonNote)
class LessonNoteAdmin(admin.ModelAdmin):
    list_display = ("subject", "strand_topic", "class_level", "week_ending", "teacher")
    list_filter = ("subject", "class_level")