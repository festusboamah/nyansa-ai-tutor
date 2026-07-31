from django.contrib import admin

from .models import CommunicationPreference, DeliveryAttempt, MessageIntent, MessageTemplate


admin.site.register(MessageTemplate)
admin.site.register(CommunicationPreference)


@admin.register(MessageIntent)
class MessageIntentAdmin(admin.ModelAdmin):
    list_display = ("recipient", "event_type", "channel", "status", "attempt_count", "created_at")
    list_filter = ("school", "status", "channel", "event_type")
    readonly_fields = ("idempotency_key", "rendered_subject", "rendered_body", "attempt_count", "provider_message_id", "sent_at")


@admin.register(DeliveryAttempt)
class DeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = ("intent", "attempt_number", "succeeded", "provider", "attempted_at")
    readonly_fields = ("intent", "attempt_number", "succeeded", "provider", "provider_message_id", "error", "attempted_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
