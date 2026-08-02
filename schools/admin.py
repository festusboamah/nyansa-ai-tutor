from django.contrib import admin

from .models import School, SchoolInvitation, SchoolMembership, StudentProfile


class SchoolMembershipInline(admin.TabularInline):
    model = SchoolMembership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "timezone", "created_at")
    list_filter = ("status", "timezone")
    search_fields = ("name", "slug", "email", "phone")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (SchoolMembershipInline,)


@admin.register(SchoolMembership)
class SchoolMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "role", "status", "identifier", "portal_access_enabled")
    list_filter = ("school", "role", "status")
    search_fields = ("user__username", "user__email", "school__name", "identifier")
    autocomplete_fields = ("school", "user")


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("membership", "gender", "date_of_birth", "guardian_phone")
    search_fields = ("membership__user__first_name", "membership__user__last_name", "membership__identifier", "guardian_name", "guardian_phone")


@admin.register(SchoolInvitation)
class SchoolInvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "school", "role", "status", "expires_at")
    list_filter = ("school", "role", "status")
    readonly_fields = ("token_digest", "accepted_at", "created_at")
