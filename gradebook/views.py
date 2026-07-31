from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from urllib.parse import quote

from academics.models import ClassEnrollment, SubjectOffering
from schools.models import SchoolMembership
from schools.services import has_school_role

from .forms import AssessmentForm, GradeWorkbookUploadForm
from .imports import confirm_grade_import
from .models import Assessment, GradeEntry, GradeImportBatch, GradeImportRow
from .spreadsheets import WorkbookValidationError, build_grade_template, parse_grade_template


def teacher_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not has_school_role(request, SchoolMembership.Role.TEACHER):
            messages.error(request, "This page is only available to teachers.")
            return redirect("home")
        return view(request, *args, **kwargs)

    return wrapped


def _assigned_offerings(request):
    return SubjectOffering.objects.filter(
        school=request.school,
        teacher_assignments__teacher=request.school_membership,
    ).select_related("subject", "school_class", "term", "term__academic_year").distinct()


def _assigned_offering(request, offering_id):
    return get_object_or_404(_assigned_offerings(request), pk=offering_id)


def _assigned_assessment(request, assessment_id):
    return get_object_or_404(
        Assessment.objects.select_related(
            "offering__subject", "offering__school_class", "offering__term", "category"
        ),
        pk=assessment_id,
        school=request.school,
        offering__teacher_assignments__teacher=request.school_membership,
    )


def _assessment_enrollments(assessment):
    return ClassEnrollment.objects.filter(
        school_class=assessment.offering.school_class,
        status=ClassEnrollment.Status.ACTIVE,
        student__status=SchoolMembership.Status.ACTIVE,
    ).select_related("student__user").order_by(
        "student__user__last_name", "student__user__first_name", "student__user__username"
    )


def _assigned_batch(request, batch_id):
    return get_object_or_404(
        GradeImportBatch.objects.select_related(
            "assessment__offering__subject", "assessment__offering__school_class", "uploaded_by__user"
        ),
        pk=batch_id,
        school=request.school,
        uploaded_by=request.school_membership,
        assessment__offering__teacher_assignments__teacher=request.school_membership,
    )


@teacher_required
def offering_list(request):
    offerings = _assigned_offerings(request).prefetch_related("assessments")
    return render(request, "gradebook/offering_list.html", {"offerings": offerings})


@teacher_required
def assessment_list(request, offering_id):
    offering = _assigned_offering(request, offering_id)
    assessments = offering.assessments.select_related("category").order_by("category__order", "due_at", "id")
    return render(request, "gradebook/assessment_list.html", {"offering": offering, "assessments": assessments})


@teacher_required
def create_assessment(request, offering_id):
    offering = _assigned_offering(request, offering_id)
    form = AssessmentForm(request.POST or None, offering=offering)
    if request.method == "POST" and form.is_valid():
        assessment = form.save(commit=False)
        try:
            assessment.full_clean()
        except ValidationError as error:
            form.add_error(None, error)
        else:
            assessment.save()
            messages.success(request, "Assessment created. You can now enter roster scores.")
            return redirect("gradebook_roster", assessment_id=assessment.pk)
    return render(request, "gradebook/assessment_form.html", {"form": form, "offering": offering})


@teacher_required
def grade_roster(request, assessment_id):
    assessment = _assigned_assessment(request, assessment_id)
    enrollments = list(_assessment_enrollments(assessment))
    existing = {
        entry.student_id: entry
        for entry in GradeEntry.objects.filter(
            school=request.school,
            assessment=assessment,
            student_id__in=[row.student_id for row in enrollments],
        )
    }
    errors = {}

    if request.method == "POST":
        if assessment.status == Assessment.Status.CLOSED:
            messages.error(request, "Closed assessments cannot be edited.")
            return redirect("gradebook_roster", assessment_id=assessment.pk)
        target_status = GradeEntry.Status.PUBLISHED if request.POST.get("action") == "publish" else GradeEntry.Status.DRAFT
        pending = []
        for enrollment in enrollments:
            raw_score = request.POST.get(f"score_{enrollment.student_id}", "").strip()
            if not raw_score:
                continue
            try:
                score = Decimal(raw_score)
            except InvalidOperation:
                errors[enrollment.student_id] = "Enter a valid number."
                continue
            if not score.is_finite():
                errors[enrollment.student_id] = "Enter a finite number."
                continue
            entry = existing.get(enrollment.student_id) or GradeEntry(
                school=request.school, assessment=assessment, student=enrollment.student
            )
            entry.score = score
            entry.recorded_by = request.school_membership
            entry.source = GradeEntry.Source.MANUAL
            entry.status = target_status
            try:
                entry.full_clean()
            except ValidationError as error:
                errors[enrollment.student_id] = "; ".join(error.messages)
            pending.append(entry)

        if not errors:
            with transaction.atomic():
                for entry in pending:
                    entry.save()
            verb = "published" if target_status == GradeEntry.Status.PUBLISHED else "saved as draft"
            noun = "entry" if len(pending) == 1 else "entries"
            messages.success(request, f"{len(pending)} grade {noun} {verb}.")
            return redirect("gradebook_roster", assessment_id=assessment.pk)

    rows = []
    for enrollment in enrollments:
        entry = existing.get(enrollment.student_id)
        rows.append({
            "membership": enrollment.student,
            "entry": entry,
            "value": request.POST.get(f"score_{enrollment.student_id}", "") if request.method == "POST" else (entry.score if entry else ""),
            "error": errors.get(enrollment.student_id),
        })
    return render(request, "gradebook/grade_roster.html", {"assessment": assessment, "rows": rows})


@teacher_required
def download_grade_template(request, assessment_id):
    assessment = _assigned_assessment(request, assessment_id)
    workbook = build_grade_template(
        assessment=assessment, enrollments=list(_assessment_enrollments(assessment))
    )
    response = HttpResponse(
        workbook.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    filename = f"{assessment.offering.school_class.name}-{assessment.title}-grades.xlsx"
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return response


@teacher_required
def upload_grade_workbook(request, assessment_id):
    assessment = _assigned_assessment(request, assessment_id)
    if assessment.status == Assessment.Status.CLOSED:
        messages.error(request, "Closed assessments cannot receive imported grades.")
        return redirect("gradebook_roster", assessment_id=assessment.pk)
    form = GradeWorkbookUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        uploaded = form.cleaned_data["workbook"]
        try:
            parsed = parse_grade_template(
                file=uploaded,
                assessment=assessment,
                enrollments=list(_assessment_enrollments(assessment)),
            )
        except WorkbookValidationError as error:
            form.add_error("workbook", str(error))
        else:
            with transaction.atomic():
                valid_count = sum(row["status"] == GradeImportRow.Status.VALID for row in parsed)
                error_count = sum(row["status"] == GradeImportRow.Status.ERROR for row in parsed)
                batch = GradeImportBatch(
                    school=request.school,
                    assessment=assessment,
                    uploaded_by=request.school_membership,
                    original_filename=uploaded.name[:255],
                    row_count=len(parsed),
                    valid_count=valid_count,
                    error_count=error_count,
                )
                batch.full_clean()
                batch.save()
                GradeImportRow.objects.bulk_create(
                    [GradeImportRow(batch=batch, **row) for row in parsed]
                )
            return redirect("gradebook_import_preview", batch_id=batch.pk)
    return render(
        request,
        "gradebook/import_upload.html",
        {"assessment": assessment, "form": form},
    )


@teacher_required
def import_preview(request, batch_id):
    batch = _assigned_batch(request, batch_id)
    return render(
        request,
        "gradebook/import_preview.html",
        {"batch": batch, "rows": batch.rows.select_related("student__user")},
    )


@teacher_required
def confirm_import(request, batch_id):
    batch = _assigned_batch(request, batch_id)
    if request.method != "POST":
        return redirect("gradebook_import_preview", batch_id=batch.pk)
    try:
        _, imported_count = confirm_grade_import(
            batch=batch,
            confirmed_by=request.school_membership,
            publish=request.POST.get("action") == "publish",
        )
    except ValidationError as error:
        messages.error(request, "; ".join(error.messages))
        return redirect("gradebook_import_preview", batch_id=batch.pk)
    messages.success(request, f"Import confirmed. {imported_count} grade entries were saved.")
    return redirect("gradebook_roster", assessment_id=batch.assessment_id)
