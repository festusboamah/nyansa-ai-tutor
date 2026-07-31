from django.contrib import admin

from .models import GuardianLink


@admin.register(GuardianLink)
class GuardianLinkAdmin(admin.ModelAdmin):
    list_display = ("guardian", "student", "relationship", "status", "is_primary_contact", "authorized_at")
    list_filter = ("school", "status", "relationship")
