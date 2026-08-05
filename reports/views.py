from functools import wraps
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from academics.models import SchoolClass, Term
from schools.models import SchoolMembership
from schools.services import has_school_role

from .forms import ReportDecisionForm, ReportDetailsForm, ReportPolicyForm
from .models import ReportPolicy, TermReport
from .pdf import render_order_of_merit_pdf, render_promotion_list_pdf, render_report_pdf
from .services import can_prepare_reports, generate_class_reports, transition_report, update_report_details


def report_staff_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not has_school_role(request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN):
            messages.error(request, "Term reports are available only to school staff.")
            return redirect("home")
        return view(request, *args, **kwargs)
    return wrapped


def _class_term(request, class_id, term_id):
    school_class = get_object_or_404(SchoolClass, pk=class_id, school=request.school)
    term = get_object_or_404(Term, pk=term_id, academic_year=school_class.academic_year)
    if not can_prepare_reports(request.school_membership, school_class, term):
        raise PermissionDenied
    return school_class, term


@report_staff_required
def report_dashboard(request):
    classes = SchoolClass.objects.filter(school=request.school).select_related("academic_year").prefetch_related("academic_year__terms")
    if request.school_membership.role == SchoolMembership.Role.TEACHER:
        classes = classes.filter(
            Q(class_teacher=request.school_membership)
            | Q(subject_offerings__teacher_assignments__teacher=request.school_membership)
        ).distinct()
    return render(request, "reports/dashboard.html", {"classes": classes})


@report_staff_required
def class_reports(request, class_id, term_id):
    school_class, term = _class_term(request, class_id, term_id)
    if request.method == "POST":
        try:
            reports = generate_class_reports(
                school_class=school_class, term=term, actor=request.school_membership
            )
        except (ValidationError, PermissionDenied) as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Prepared {len(reports)} report snapshots.")
        return redirect("class_term_reports", class_id=class_id, term_id=term_id)
    reports = TermReport.objects.filter(school_class=school_class, term=term).select_related("student__user")
    return render(request, "reports/class_reports.html", {
        "school_class": school_class, "term": term, "reports": reports,
    })


@report_staff_required
def report_detail(request, report_id):
    report = get_object_or_404(
        TermReport.objects.select_related("student__user", "school_class", "term"),
        pk=report_id, school=request.school,
    )
    if not can_prepare_reports(request.school_membership, report.school_class, report.term):
        raise PermissionDenied
    is_admin = request.school_membership.role == SchoolMembership.Role.SCHOOL_ADMIN
    details_form = ReportDetailsForm(request.POST or None, instance=report, is_admin=is_admin)
    if is_admin:
        actions = {
            TermReport.Status.DRAFT: [("approve", "Approve as administrator")],
            TermReport.Status.RETURNED: [("approve", "Approve as administrator")],
            TermReport.Status.PENDING: [("approve", "Approve"), ("return", "Send back")],
            TermReport.Status.APPROVED: [("publish", "Publish")],
            TermReport.Status.PUBLISHED: [("reopen", "Reopen published report")],
        }.get(report.status, [])
    else:
        actions = (
            [("submit", "Submit for administrator review")]
            if report.status in {TermReport.Status.DRAFT, TermReport.Status.RETURNED}
            else []
        )
    decision_form = ReportDecisionForm(actions=actions)
    if request.method == "POST" and request.POST.get("form_type") == "details" and details_form.is_valid():
        try:
            update_report_details(
                report=report, actor=request.school_membership,
                conduct=details_form.cleaned_data.get("conduct"),
                teacher_remark=details_form.cleaned_data.get("teacher_remark"),
                promotion_outcome=details_form.cleaned_data["promotion_outcome"],
                administrator_remark=details_form.cleaned_data.get("administrator_remark"),
            )
        except (ValidationError, PermissionDenied) as error:
            details_form.add_error(None, str(error))
        else:
            messages.success(request, "Report details saved.")
            return redirect("term_report_detail", report_id=report.pk)
    elif request.method == "POST" and request.POST.get("form_type") == "decision":
        decision_form = ReportDecisionForm(request.POST, actions=actions)
        if decision_form.is_valid():
            try:
                transition_report(
                    report=report, actor=request.school_membership,
                    action=decision_form.cleaned_data["action"], note=decision_form.cleaned_data["note"],
                )
            except (ValidationError, PermissionDenied) as error:
                decision_form.add_error(None, str(error))
            else:
                messages.success(request, "Report workflow updated.")
                return redirect("term_report_detail", report_id=report.pk)
    report.refresh_from_db()
    return render(request, "reports/detail.html", {
        "report": report, "data": report.snapshot, "details_form": details_form,
        "decision_form": decision_form, "workflow_actions": actions,
    })


@report_staff_required
def report_pdf(request, report_id):
    report = get_object_or_404(TermReport, pk=report_id, school=request.school)
    if not can_prepare_reports(request.school_membership, report.school_class, report.term):
        raise PermissionDenied
    content = render_report_pdf(report)
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="term-report-{report.pk}.pdf"'
    return response


@report_staff_required
def class_reports_zip(request, class_id, term_id):
    school_class, term = _class_term(request, class_id, term_id)
    reports = TermReport.objects.filter(
        school_class=school_class, term=term, status=TermReport.Status.PUBLISHED
    ).select_related("student__user")
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for report in reports.iterator():
            name = slugify(report.snapshot.get("student", {}).get("name", "student")) or f"student-{report.student_id}"
            archive.writestr(f"{name}-term-report.pdf", render_report_pdf(report))
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{slugify(school_class.name)}-{slugify(term.name)}-reports.zip"'
    return response


@report_staff_required
def order_of_merit_pdf(request, class_id, term_id):
    school_class, term = _class_term(request, class_id, term_id)
    reports = list(TermReport.objects.filter(
        school_class=school_class, term=term, status=TermReport.Status.PUBLISHED
    ).select_related("student__user"))
    content = render_order_of_merit_pdf(
        school_class=school_class, term=term, reports=reports
    )
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="{slugify(school_class.name)}-{slugify(term.name)}-order-of-merit.pdf"'
    )
    return response


@report_staff_required
def promotion_list_pdf(request, class_id, term_id):
    if request.school_membership.role != SchoolMembership.Role.SCHOOL_ADMIN:
        raise PermissionDenied
    school_class, term = _class_term(request, class_id, term_id)
    reports = list(TermReport.objects.filter(
        school_class=school_class, term=term, status=TermReport.Status.PUBLISHED
    ).select_related("student__user"))
    content = render_promotion_list_pdf(
        school_class=school_class, term=term, reports=reports
    )
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="{slugify(school_class.name)}-{slugify(term.name)}-promotion-list.pdf"'
    )
    return response


@report_staff_required
def report_policy(request, year_id):
    if request.school_membership.role != SchoolMembership.Role.SCHOOL_ADMIN:
        raise PermissionDenied
    year = get_object_or_404(request.school.academic_years, pk=year_id)
    policy, _ = ReportPolicy.objects.get_or_create(school=request.school, academic_year=year)
    form = ReportPolicyForm(request.POST or None, instance=policy)
    if request.method == "POST" and form.is_valid():
        updated = form.save(commit=False)
        updated.school, updated.academic_year = request.school, year
        updated.full_clean()
        updated.save()
        messages.success(request, "Report policy updated.")
        return redirect("term_report_dashboard")
    return render(request, "reports/policy.html", {"form": form, "year": year})
