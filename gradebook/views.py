from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from academics.models import ClassEnrollment, SubjectOffering
from schools.models import SchoolMembership
from schools.services import has_school_role

from .forms import AssessmentForm
from .models import Assessment, GradeEntry


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
    enrollments = list(
        ClassEnrollment.objects.filter(
            school_class=assessment.offering.school_class,
            status=ClassEnrollment.Status.ACTIVE,
            student__status=SchoolMembership.Status.ACTIVE,
        ).select_related("student__user").order_by(
            "student__user__last_name", "student__user__first_name", "student__user__username"
        )
    )
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
