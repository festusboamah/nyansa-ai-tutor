from django.contrib import admin

from .models import Assessment, AssessmentCategory, GradeEntry, GradeEntryRevision, GradeImportBatch, GradeImportRow, GradeReviewDecision, GradeScheme


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
    list_filter = ("status", "school", "category", "topic")


@admin.register(GradeEntry)
class GradeEntryAdmin(admin.ModelAdmin):
    list_display = ("assessment", "student", "score", "source", "status", "review_status", "recorded_by")
    list_filter = ("source", "status", "review_status", "school")


@admin.register(GradeEntryRevision)
class GradeEntryRevisionAdmin(admin.ModelAdmin):
    list_display = ("entry", "change_type", "previous_score", "new_score", "changed_by", "changed_at")
    readonly_fields = (
        "entry", "change_type", "previous_score", "new_score", "previous_status", "new_status",
        "previous_source", "new_source", "reason", "changed_by", "changed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GradeReviewDecision)
class GradeReviewDecisionAdmin(admin.ModelAdmin):
    list_display = ("entry", "decision", "reviewed_by", "reviewed_at")
    readonly_fields = ("entry", "decision", "note", "reviewed_by", "reviewed_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
