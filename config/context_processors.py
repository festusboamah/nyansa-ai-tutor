from django.conf import settings


def deployment_mode(request):
    context = {"nyansa_demo_mode": settings.NYANSA_DEMO_MODE}
    membership = getattr(request, "school_membership", None)
    if membership and membership.role in {"TEACHER", "SCHOOL_ADMIN"}:
        notifications = membership.notifications.all()
        context.update({
            "staff_notification_unread_count": notifications.filter(read_at__isnull=True).count(),
            "staff_notification_preview": notifications[:5],
        })
    return context
