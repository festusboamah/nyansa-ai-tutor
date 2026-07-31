from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User
from schools.models import SchoolMembership


class SchoolMembershipInline(admin.TabularInline):
    model = SchoolMembership
    extra = 0


class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("Role Info", {"fields": ("role",)}),
    )
    inlines = (SchoolMembershipInline,)


admin.site.register(User, CustomUserAdmin)
