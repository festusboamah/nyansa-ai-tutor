from django.conf import settings


def deployment_mode(request):
    context = {"nyansa_demo_mode": settings.NYANSA_DEMO_MODE}
    membership = getattr(request, "school_membership", None)
    if membership and membership.role in {"TEACHER", "SCHOOL_ADMIN"}:
        notifications = membership.notifications.filter(archived_at__isnull=True)
        context.update({
            "staff_notification_unread_count": notifications.filter(read_at__isnull=True).count(),
            "staff_notification_preview": notifications[:5],
        })
        if membership.role == "SCHOOL_ADMIN":
            from dashboard.models import LessonNote
            from gradebook.models import GradeEntry
            from reports.models import TermReport

            context["admin_pending_work"] = {
                "lessons": LessonNote.objects.filter(
                    subject__school=membership.school, status=LessonNote.Status.PENDING_REVIEW
                ).count(),
                "grades": GradeEntry.objects.filter(
                    school=membership.school, review_status=GradeEntry.ReviewStatus.PENDING
                ).count(),
                "reports": TermReport.objects.filter(
                    school=membership.school, status=TermReport.Status.PENDING
                ).count(),
            }
    return context
