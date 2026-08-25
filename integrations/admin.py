from django.contrib import admin
from .models import IntegrationCredential, Suku360RosterCredential, SyncBatch, SyncRecord


@admin.register(IntegrationCredential)
class IntegrationCredentialAdmin(admin.ModelAdmin):
    list_display = ("school", "created_by", "created_at", "last_used_at", "is_active")
    list_filter = ("is_active",)


@admin.register(Suku360RosterCredential)
class Suku360RosterCredentialAdmin(admin.ModelAdmin):
    list_display = ("school", "base_url", "is_active", "updated_at")
    list_filter = ("is_active",)


class SyncRecordInline(admin.TabularInline):
    model = SyncRecord
    extra = 0
    readonly_fields = ("entity_type", "suku360_id", "nyansa_object_id", "action", "error_message", "created_at")
    can_delete = False


@admin.register(SyncBatch)
class SyncBatchAdmin(admin.ModelAdmin):
    list_display = ("school", "status", "started_at", "completed_at")
    list_filter = ("status",)
    inlines = [SyncRecordInline]
