from django.contrib import admin
from .models import RemediationPlan, StudyGoal, Strand, Topic, TopicRevision


class TopicInline(admin.TabularInline):
    model = Topic
    extra = 0


@admin.register(Strand)
class StrandAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "school", "order")
    list_filter = ("school", "subject")
    inlines = [TopicInline]


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("name", "strand", "order")
    list_filter = ("strand__subject",)
    filter_horizontal = ("prerequisites",)


@admin.register(TopicRevision)
class TopicRevisionAdmin(admin.ModelAdmin):
    list_display = ("topic", "previous_name", "new_name", "reason", "changed_by", "changed_at")
    list_filter = ("topic__strand__subject",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RemediationPlan)
class RemediationPlanAdmin(admin.ModelAdmin):
    list_display = (
        "student", "topic", "status", "mastery_percentage_at_start",
        "mastery_percentage_at_completion", "created_by", "created_at",
    )
    list_filter = ("status", "topic__strand__subject")


@admin.register(StudyGoal)
class StudyGoalAdmin(admin.ModelAdmin):
    list_display = ("student", "topic", "status", "created_at", "achieved_at")
    list_filter = ("status", "topic__strand__subject")
