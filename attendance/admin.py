from django.contrib import admin

from .models import AttendanceRecord, AttendanceRevision, AttendanceSession, SchoolCalendarPolicy, SchoolClosure


admin.site.register([SchoolCalendarPolicy, SchoolClosure, AttendanceSession, AttendanceRecord])


@admin.register(AttendanceRevision)
class AttendanceRevisionAdmin(admin.ModelAdmin):
    list_display = ("record", "previous_status", "new_status", "changed_by", "changed_at")
    readonly_fields = ("record", "previous_status", "new_status", "reason", "changed_by", "changed_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
