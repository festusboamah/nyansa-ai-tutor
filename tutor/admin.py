from django.contrib import admin
from .models import TutorSession, TutorMessage, TutorUsageEvent


@admin.register(TutorSession)
class TutorSessionAdmin(admin.ModelAdmin):
    list_display = ("title", "student", "school", "mode", "created_at")
    list_filter = ("mode", "school")
    search_fields = ("title", "student__username")


@admin.register(TutorMessage)
class TutorMessageAdmin(admin.ModelAdmin):
    list_display = ("session", "role", "created_at")
    list_filter = ("role",)


@admin.register(TutorUsageEvent)
class TutorUsageEventAdmin(admin.ModelAdmin):
    list_display = ("session", "model", "succeeded", "input_tokens", "output_tokens", "created_at")
    list_filter = ("succeeded", "model")
