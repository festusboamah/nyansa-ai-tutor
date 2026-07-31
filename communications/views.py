from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from guardians.models import GuardianLink
from schools.models import SchoolMembership
from schools.services import has_school_role

from .forms import CommunicationPreferenceForm, MessageTemplateForm, SchoolEventForm
from .models import CommunicationPreference, MessageIntent, MessageTemplate
from .services import enqueue_message, ensure_default_templates


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
