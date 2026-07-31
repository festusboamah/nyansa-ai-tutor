from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from academics.models import ClassEnrollment
from attendance.services import student_attendance_summary
from reports.models import TermReport
from reports.pdf import render_report_pdf
from schools.models import SchoolMembership
from schools.services import has_school_role

from .forms import GuardianLinkForm
from .models import GuardianLink
from .services import authorize_link, guardian_can_access, linked_students, revoke_link


def guardian_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not has_school_role(request, SchoolMembership.Role.PARENT):
            messages.error(request, "The guardian portal is available only to verified guardian accounts.")
            return redirect("home")
        return view(request, *args, **kwargs)
    return wrapped


@guardian_required
def portal(request):
    return render(request, "guardians/portal.html", {"students": linked_students(request.school_membership)})


@guardian_required
def student_detail(request, student_id):
    student = get_object_or_404(linked_students(request.school_membership), pk=student_id)
    enrollments = ClassEnrollment.objects.filter(student=student).select_related("school_class__academic_year")
    attendance = []
    for enrollment in enrollments:
        for term in enrollment.school_class.academic_year.terms.all():
            attendance.append({
                "term": term,
                "school_class": enrollment.school_class,
                "summary": student_attendance_summary(
                    student=student, term=term, school_class=enrollment.school_class, through=term.end_date
                ),
            })
    reports = TermReport.objects.filter(
        school=request.school, student=student, status=TermReport.Status.PUBLISHED
    ).select_related("term", "school_class")
    return render(request, "guardians/student_detail.html", {
        "student": student, "reports": reports, "attendance": attendance,
    })


@guardian_required
def published_report_pdf(request, report_id):
    report = get_object_or_404(
        TermReport, pk=report_id, school=request.school, status=TermReport.Status.PUBLISHED
    )
    if not guardian_can_access(request.school_membership, report.student):
        raise PermissionDenied
    response = HttpResponse(render_report_pdf(report), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="term-report-{report.pk}.pdf"'
    return response


@login_required
def manage_links(request):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied
    form = GuardianLinkForm(request.POST or None, school=request.school)
    if request.method == "POST" and form.is_valid():
        try:
            authorize_link(
                school=request.school, guardian=form.cleaned_data["guardian"],
                student=form.cleaned_data["student"], relationship=form.cleaned_data["relationship"],
                is_primary_contact=form.cleaned_data["is_primary_contact"],
                authorization_reference=form.cleaned_data["authorization_reference"],
                actor=request.school_membership,
            )
        except (ValidationError, PermissionDenied) as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Guardian access authorized.")
            return redirect("guardian_links")
    links = GuardianLink.objects.filter(school=request.school).select_related("guardian__user", "student__user")
    return render(request, "guardians/manage_links.html", {"form": form, "links": links})


@login_required
def revoke_link_view(request, link_id):
    if request.method != "POST" or not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied
    link = get_object_or_404(GuardianLink, pk=link_id, school=request.school)
    try:
        revoke_link(link=link, actor=request.school_membership)
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Guardian access revoked.")
    return redirect("guardian_links")

