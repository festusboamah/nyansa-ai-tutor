from django.contrib import admin

from .models import Assessment, AssessmentCategory, GradeEntry, GradeImportBatch, GradeImportRow, GradeScheme


class AssessmentCategoryInline(admin.TabularInline):
    model = AssessmentCategory
    extra = 0


@admin.register(GradeScheme)
class GradeSchemeAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "academic_year", "status")
    list_filter = ("status", "school")
    inlines = [AssessmentCategoryInline]


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("title", "school", "offering", "category", "max_score", "status")
    list_filter = ("status", "school", "category")


@admin.register(GradeEntry)
class GradeEntryAdmin(admin.ModelAdmin):
    list_display = ("assessment", "student", "score", "source", "status", "recorded_by")
    list_filter = ("source", "status", "school")


class GradeImportRowInline(admin.TabularInline):
    model = GradeImportRow
    extra = 0
    readonly_fields = ("row_number", "student", "raw_student_id", "raw_score", "score", "status", "error")


@admin.register(GradeImportBatch)
class GradeImportBatchAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "school", "assessment", "status", "valid_count", "error_count", "uploaded_at")
    list_filter = ("status", "school")
    readonly_fields = ("row_count", "valid_count", "error_count", "uploaded_at", "confirmed_at")
    inlines = [GradeImportRowInline]
