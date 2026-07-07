from django.contrib import admin
from .models import Subject, Material


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "teacher", "material_type", "uploaded_at")
    list_filter = ("material_type", "subject")
    search_fields = ("title",)