from django.contrib import admin
from .models import IntegrationCredential


@admin.register(IntegrationCredential)
class IntegrationCredentialAdmin(admin.ModelAdmin):
    list_display = ("school", "created_by", "created_at", "last_used_at", "is_active")
    list_filter = ("is_active",)
