from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from guardians.models import GuardianLink
from schools.models import SchoolMembership
from schools.services import has_school_role

from .forms import CommunicationPreferenceForm, MessageTemplateForm, SchoolEventForm
from .models import CommunicationPreference, MessageIntent, MessageTemplate, Notification
from .services import archive_stale_notifications, enqueue_message, ensure_default_templates


def _require_staff_membership(request):
    membership = getattr(request, "school_membership", None)
    if not membership or membership.role not in {
        SchoolMembership.Role.TEACHER,
        SchoolMembership.Role.SCHOOL_ADMIN,
    }:
        raise PermissionDenied
    return membership


@login_required
def notification_center(request):
    membership = _require_staff_membership(request)
    archive_stale_notifications(recipient=membership)
    notifications = Notification.objects.filter(recipient=membership, archived_at__isnull=True)
    selected_kind = request.GET.get("kind", "")
    unread_only = request.GET.get("unread") == "1"
    if selected_kind in Notification.Kind.values:
        notifications = notifications.filter(kind=selected_kind)
    else:
        selected_kind = ""
    if unread_only:
        notifications = notifications.filter(read_at__isnull=True)
    return render(request, "communications/notifications.html", {
        "notifications": notifications,
        "notification_kinds": Notification.Kind.choices,
        "selected_kind": selected_kind,
        "unread_only": unread_only,
    })


@login_required
def notification_read(request, notification_id):
    membership = _require_staff_membership(request)
    notification = get_object_or_404(
        Notification, pk=notification_id, recipient=membership, archived_at__isnull=True
    )
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return redirect(notification.target_url)


@login_required
def notification_mark_all_read(request):
    membership = _require_staff_membership(request)
    if request.method == "POST":
        Notification.objects.filter(
            recipient=membership, archived_at__isnull=True, read_at__isnull=True
        ).update(read_at=timezone.now())
    return redirect("notification_center")


@login_required
def preferences(request):
    if not has_school_role(request, SchoolMembership.Role.PARENT):
        raise PermissionDenied
    preference, _ = CommunicationPreference.objects.get_or_create(recipient=request.school_membership)
    form = CommunicationPreferenceForm(request.POST or None, instance=preference)
    if request.method == "POST" and form.is_valid():
        updated = form.save(commit=False)
        updated.recipient = request.school_membership
        try:
            updated.full_clean()
        except ValidationError as error:
            form.add_error(None, error)
        else:
            updated.save()
            messages.success(request, "Communication preferences updated.")
            return redirect("communication_preferences")
    return render(request, "communications/preferences.html", {"form": form})


@login_required
def admin_dashboard(request):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied
    ensure_default_templates(request.school)
    return render(request, "communications/dashboard.html", {
        "templates": MessageTemplate.objects.filter(school=request.school),
        "intents": MessageIntent.objects.filter(school=request.school).select_related("recipient__user", "template")[:100],
    })


@login_required
def template_edit(request, template_id=None):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied
    template = get_object_or_404(MessageTemplate, pk=template_id, school=request.school) if template_id else None
    form = MessageTemplateForm(request.POST or None, instance=template)
    if request.method == "POST" and form.is_valid():
        updated = form.save(commit=False)
        updated.school = request.school
        try:
            updated.full_clean()
        except ValidationError as error:
            form.add_error(None, error)
        else:
            updated.save()
            messages.success(request, "Message template saved.")
            return redirect("communications_dashboard")
    return render(request, "communications/template_form.html", {"form": form, "template": template})


@login_required
def send_school_event(request):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied
    form = SchoolEventForm(request.POST or None, school=request.school)
    if request.method == "POST" and form.is_valid():
        templates = ensure_default_templates(request.school)
        queued = 0
        event_reference = f"school-event:{request.school.id}:{form.cleaned_data['title']}:{request.POST.get('event_key', '')}"
        for guardian in form.cleaned_data["guardians"]:
            context = {
                "school_name": request.school.name,
                "event_title": form.cleaned_data["title"],
                "event_message": form.cleaned_data["message"],
            }
            intent = enqueue_message(
                template=templates["school-event-email"], recipient=guardian,
                business_reference=event_reference, context=context,
            )
            queued += bool(intent)
        messages.success(request, f"Queued {queued} event message(s).")
        return redirect("communications_dashboard")
    return render(request, "communications/school_event.html", {"form": form})
