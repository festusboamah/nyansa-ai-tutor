from django.contrib import admin
from .models import Subject, Material, Enrollment


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "created_at")
    list_filter = ("school",)
    search_fields = ("name", "school__name")


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "teacher", "material_type", "uploaded_at")
    list_filter = ("material_type", "subject__school", "subject")
    search_fields = ("title",)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "enrolled_at")
    list_filter = ("subject__school", "subject")
