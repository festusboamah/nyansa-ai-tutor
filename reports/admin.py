from django.contrib import admin

from .models import ReportPolicy, ReportWorkflowEvent, TermReport


@admin.register(ReportPolicy)
class ReportPolicyAdmin(admin.ModelAdmin):
    list_display = ("school", "academic_year", "show_position", "pass_mark", "promotion_average")


@admin.register(TermReport)
class TermReportAdmin(admin.ModelAdmin):
    list_display = ("student", "school_class", "term", "status", "average_score", "version")
    list_filter = ("school", "status", "term")


@admin.register(ReportWorkflowEvent)
class ReportWorkflowEventAdmin(admin.ModelAdmin):
    list_display = ("report", "action", "actor", "occurred_at")
    readonly_fields = ("report", "action", "from_status", "to_status", "note", "actor", "occurred_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
