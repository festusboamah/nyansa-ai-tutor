from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from schools.models import SchoolMembership
from schools.services import has_school_role

from .services import school_ai_usage


@login_required
def ai_usage_report_view(request):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        messages.error(request, "Only school administrators can view AI usage.")
        return redirect("home")

    usage = school_ai_usage(request.school)
    return render(request, "ai_core/usage_report.html", {"usage": usage})
