from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, IntegerField, When
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from urllib.parse import quote

from academics.models import AcademicYear, ClassEnrollment, SubjectOffering
from schools.models import SchoolMembership
from schools.services import has_school_role

from .forms import AssessmentForm, GradeCorrectionForm, GradeWorkbookUploadForm
from .history import record_grade_entry, review_grade_entry
from .imports import confirm_grade_import
from .models import Assessment, GradeEntry, GradeImportBatch, GradeImportRow, GradeReviewDecision, GradeScheme
from .services import configure_ges_grade_scheme
from .spreadsheets import WorkbookValidationError, build_grade_template, parse_grade_template
from .sync import sync_legacy_assessment


def teacher_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not has_school_role(request, SchoolMembership.Role.TEACHER):
            messages.error(request, "This page is only available to teachers.")
            return redirect("home")
        return view(request, *args, **kwargs)

    return wrapped


def school_admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
            messages.error(request, "This page is only available to school administrators.")
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
    form = AssessmentForm(request.POST or None, offering=offering, teacher_user=request.user)
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
            existing_entry = existing.get(enrollment.student_id)
            if existing_entry and existing_entry.review_status == GradeEntry.ReviewStatus.APPROVED:
                errors[enrollment.student_id] = "Approved grade must be returned before correction."
            elif existing_entry and existing_entry.status == GradeEntry.Status.PUBLISHED and (
                existing_entry.score != score
                or existing_entry.status != target_status
                or existing_entry.source != GradeEntry.Source.MANUAL
            ):
                errors[enrollment.student_id] = "Use the correction page to change a published grade."
            entry = existing_entry or GradeEntry(
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
                    record_grade_entry(
                        school=request.school,
                        assessment=assessment,
                        student=entry.student,
                        actor=request.school_membership,
                        score=entry.score,
                        source=GradeEntry.Source.MANUAL,
                        status=entry.status,
                        reason="Manual roster entry" if entry.pk is None else "Updated draft roster entry",
                    )
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
    entries = list(existing.values())
    return render(request, "gradebook/grade_roster.html", {
        "assessment": assessment,
        "rows": rows,
        "entered_count": len(entries),
        "missing_count": max(len(enrollments) - len(entries), 0),
        "published_count": sum(entry.status == GradeEntry.Status.PUBLISHED for entry in entries),
        "pending_count": sum(entry.review_status == GradeEntry.ReviewStatus.PENDING for entry in entries),
    })


@teacher_required
def correct_grade(request, entry_id):
    entry = get_object_or_404(
        GradeEntry.objects.select_related("assessment__offering", "student__user").prefetch_related(
            "revisions__changed_by__user", "review_decisions__reviewed_by__user"
        ),
        pk=entry_id,
        school=request.school,
        assessment__offering__teacher_assignments__teacher=request.school_membership,
    )
    form = GradeCorrectionForm(
        request.POST or None,
        entry=entry,
        initial={"score": entry.score, "status": entry.status},
    )
    if request.method == "POST" and form.is_valid():
        try:
            record_grade_entry(
                school=request.school,
                assessment=entry.assessment,
                student=entry.student,
                actor=request.school_membership,
                score=form.cleaned_data["score"],
                source=GradeEntry.Source.MANUAL,
                status=form.cleaned_data["status"],
                reason=form.cleaned_data["reason"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Grade corrected and revision history recorded.")
            return redirect("gradebook_roster", assessment_id=entry.assessment_id)
    return render(request, "gradebook/grade_correction.html", {"entry": entry, "form": form})


@teacher_required
def sync_assessment(request, assessment_id):
    assessment = _assigned_assessment(request, assessment_id)
    if request.method != "POST":
        return redirect("gradebook_roster", assessment_id=assessment.pk)
    try:
        result = sync_legacy_assessment(assessment=assessment, actor=request.school_membership)
    except ValidationError as error:
        messages.error(request, "; ".join(error.messages))
    else:
        messages.success(
            request,
            f"Found {result['found']} legacy result(s): {result['changed']} synchronized and {result['unchanged']} unchanged.",
        )
    return redirect("gradebook_roster", assessment_id=assessment.pk)


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


@school_admin_required
def grade_review_queue(request):
    base_entries = GradeEntry.objects.filter(
        school=request.school, status=GradeEntry.Status.PUBLISHED
    )
    counts = {
        "total": base_entries.count(),
        "pending": base_entries.filter(review_status=GradeEntry.ReviewStatus.PENDING).count(),
        "returned": base_entries.filter(review_status=GradeEntry.ReviewStatus.RETURNED).count(),
        "approved": base_entries.filter(review_status=GradeEntry.ReviewStatus.APPROVED).count(),
    }
    classes = base_entries.values(
        "assessment__offering__school_class_id",
        "assessment__offering__school_class__name",
    ).distinct().order_by("assessment__offering__school_class__name")
    subjects = base_entries.values(
        "assessment__offering__subject_id",
        "assessment__offering__subject__name",
    ).distinct().order_by("assessment__offering__subject__name")
    selected_status = request.GET.get("status", "")
    selected_class = request.GET.get("class", "")
    selected_subject = request.GET.get("subject", "")
    entries = base_entries
    if selected_status in GradeEntry.ReviewStatus.values:
        entries = entries.filter(review_status=selected_status)
    else:
        selected_status = ""
    if selected_class.isdigit():
        entries = entries.filter(assessment__offering__school_class_id=selected_class)
    else:
        selected_class = ""
    if selected_subject.isdigit():
        entries = entries.filter(assessment__offering__subject_id=selected_subject)
    else:
        selected_subject = ""
    entries = entries.select_related(
        "student__user", "assessment__offering__subject", "assessment__offering__school_class", "recorded_by__user"
    ).annotate(
        review_priority=Case(
            When(review_status=GradeEntry.ReviewStatus.PENDING, then=0),
            When(review_status=GradeEntry.ReviewStatus.RETURNED, then=1),
            When(review_status=GradeEntry.ReviewStatus.NOT_REVIEWED, then=2),
            default=3,
            output_field=IntegerField(),
        )
    ).order_by("review_priority", "assessment__offering__school_class__name", "student__user__username")
    return render(request, "gradebook/review_queue.html", {
        "entries": entries,
        "counts": counts,
        "classes": classes,
        "subjects": subjects,
        "selected_status": selected_status,
        "selected_class": selected_class,
        "selected_subject": selected_subject,
        "review_status_choices": GradeEntry.ReviewStatus.choices,
    })


@school_admin_required
def grade_settings(request):
    years = AcademicYear.objects.filter(school=request.school).order_by("-start_date")
    selected_year = years.filter(pk=request.POST.get("academic_year") or request.GET.get("academic_year")).first()
    if selected_year is None:
        selected_year = years.filter(is_current=True).first() or years.first()
    if request.method == "POST":
        if selected_year is None:
            messages.error(request, "Create an academic year before configuring grades.")
        else:
            configure_ges_grade_scheme(selected_year)
            messages.success(
                request,
                f"GES 50/50 grading is active for {selected_year.name}. Teachers can now create Class Score and Examination assessments.",
            )
            return redirect(f"{request.path}?academic_year={selected_year.pk}")
    active_scheme = None
    if selected_year is not None:
        active_scheme = GradeScheme.objects.filter(
            school=request.school,
            academic_year=selected_year,
            status=GradeScheme.Status.ACTIVE,
        ).prefetch_related("categories").first()
    return render(request, "gradebook/grade_settings.html", {
        "years": years,
        "selected_year": selected_year,
        "active_scheme": active_scheme,
    })


@school_admin_required
def review_grade(request, entry_id):
    entry = get_object_or_404(GradeEntry, pk=entry_id, school=request.school)
    if request.method != "POST":
        return redirect("gradebook_review_queue")
    decision = request.POST.get("decision", "")
    note = request.POST.get("note", "")
    try:
        review_grade_entry(entry=entry, reviewer=request.school_membership, decision=decision, note=note)
    except ValidationError as error:
        messages.error(request, "; ".join(error.messages))
    else:
        messages.success(request, f"Grade {decision.lower()}.")
    return redirect("gradebook_review_queue")
