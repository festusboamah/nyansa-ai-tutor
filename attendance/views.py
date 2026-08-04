from datetime import date
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from academics.models import AcademicYear, ClassEnrollment, SchoolClass, Term
from schools.models import SchoolMembership
from schools.services import has_school_role

from .forms import AttendanceCorrectionForm, CalendarPolicyForm, SchoolClosureForm
from .models import AttendanceRecord, AttendanceSession, SchoolCalendarPolicy, SchoolClosure
from .services import (
    can_manage_class_attendance,
    correct_attendance,
    instructional_day_count,
    instructional_dates,
    student_attendance_summary,
    submit_attendance,
)


def attendance_staff_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not has_school_role(
            request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN
        ):
            messages.error(request, "Attendance is available only to teachers and school administrators.")
            return redirect("home")
        return view(request, *args, **kwargs)

    return wrapped


def calendar_admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
            messages.error(request, "Calendar settings are available only to school administrators.")
            return redirect("home")
        return view(request, *args, **kwargs)

    return wrapped


def _manageable_classes(request):
    queryset = SchoolClass.objects.filter(school=request.school).select_related("academic_year", "class_teacher")
    if request.school_membership.role == SchoolMembership.Role.SCHOOL_ADMIN:
        return queryset
    return queryset.filter(
        Q(class_teacher=request.school_membership)
        | Q(subject_offerings__teacher_assignments__teacher=request.school_membership)
    ).distinct()


def _manageable_class_term(request, class_id, term_id):
    school_class = get_object_or_404(_manageable_classes(request), pk=class_id)
    term = get_object_or_404(
        Term, pk=term_id, academic_year=school_class.academic_year, academic_year__school=request.school
    )
    if not can_manage_class_attendance(request.school_membership, school_class, term):
        raise PermissionDenied
    return school_class, term


@attendance_staff_required
def attendance_dashboard(request):
    manageable = _manageable_classes(request)
    years = AcademicYear.objects.filter(school=request.school, classes__in=manageable).distinct().order_by("-is_current", "-start_date")
    selected_year = years.filter(pk=request.GET.get("year")).first() if request.GET.get("year", "").isdigit() else None
    selected_year = selected_year or years.first()
    classes = manageable.filter(academic_year=selected_year) if selected_year else manageable.none()
    if classes.exclude(name="Demo Class").exists():
        classes = classes.exclude(name="Demo Class")
    terms = Term.objects.filter(academic_year=selected_year) if selected_year else Term.objects.none()
    if terms.exclude(name="Demo Term").exists():
        terms = terms.exclude(name="Demo Term")
    classes = classes.prefetch_related(Prefetch("academic_year__terms", queryset=terms))
    return render(request, "attendance/dashboard.html", {"classes": classes, "years": years, "selected_year": selected_year})


@attendance_staff_required
def class_attendance_summary(request, class_id, term_id):
    school_class, term = _manageable_class_term(request, class_id, term_id)
    through = min(date.today(), term.end_date)
    valid_dates = instructional_dates(term, through=through)
    roster = ClassEnrollment.objects.filter(
        school_class=school_class, status=ClassEnrollment.Status.ACTIVE
    ).select_related("student__user")
    rows = [
        {"student": enrollment.student, "summary": student_attendance_summary(
            student=enrollment.student, term=term, school_class=school_class, through=through
        )}
        for enrollment in roster
    ]
    return render(request, "attendance/class_summary.html", {
        "school_class": school_class,
        "term": term,
        "rows": rows,
        "days_open": instructional_day_count(term, through=through),
        "sessions": AttendanceSession.objects.filter(
            school_class=school_class,
            term=term,
            status=AttendanceSession.Status.SUBMITTED,
            attendance_date__in=valid_dates,
        ).prefetch_related("records"),
        "today": date.today(),
    })


@attendance_staff_required
def attendance_register(request, class_id, term_id):
    school_class, term = _manageable_class_term(request, class_id, term_id)
    raw_date = request.POST.get("attendance_date") or request.GET.get("date") or date.today().isoformat()
    try:
        attendance_date = date.fromisoformat(raw_date)
    except ValueError:
        attendance_date = date.today()
    roster = list(ClassEnrollment.objects.filter(
        school_class=school_class,
        status=ClassEnrollment.Status.ACTIVE,
        student__status=SchoolMembership.Status.ACTIVE,
    ).select_related("student__user"))
    session = AttendanceSession.objects.filter(
        school_class=school_class, attendance_date=attendance_date
    ).prefetch_related("records__student__user").first()
    if request.method == "POST":
        statuses = {
            enrollment.student_id: request.POST.get(f"status_{enrollment.student_id}", "")
            for enrollment in roster
        }
        try:
            session = submit_attendance(
                school_class=school_class,
                term=term,
                attendance_date=attendance_date,
                actor=request.school_membership,
                statuses=statuses,
            )
        except (ValidationError, PermissionDenied) as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Attendance register submitted.")
            return redirect("class_attendance_summary", class_id=school_class.pk, term_id=term.pk)
    records = {record.student_id: record for record in session.records.all()} if session else {}
    rows = [{"student": item.student, "record": records.get(item.student_id)} for item in roster]
    return render(request, "attendance/register.html", {
        "school_class": school_class,
        "term": term,
        "attendance_date": attendance_date,
        "session": session,
        "rows": rows,
        "status_choices": AttendanceRecord.Status.choices,
    })


@attendance_staff_required
def correct_attendance_view(request, record_id):
    record = get_object_or_404(
        AttendanceRecord.objects.select_related(
            "student__user", "session__school_class", "session__term"
        ),
        pk=record_id,
        session__school=request.school,
    )
    if not can_manage_class_attendance(
        request.school_membership, record.session.school_class, record.session.term
    ):
        raise PermissionDenied
    form = AttendanceCorrectionForm(request.POST or None, initial={"status": record.status})
    if request.method == "POST" and form.is_valid():
        try:
            correct_attendance(
                record=record,
                actor=request.school_membership,
                new_status=form.cleaned_data["status"],
                reason=form.cleaned_data["reason"],
            )
        except (ValidationError, PermissionDenied) as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Attendance correction recorded.")
            register_url = reverse(
                "attendance_register",
                args=[record.session.school_class_id, record.session.term_id],
            )
            return redirect(f"{register_url}?date={record.session.attendance_date.isoformat()}")
    return render(request, "attendance/correction.html", {"record": record, "form": form})


@calendar_admin_required
def calendar_settings(request):
    policy, _ = SchoolCalendarPolicy.objects.get_or_create(school=request.school)
    form = CalendarPolicyForm(request.POST or None, instance=policy)
    if request.method == "POST" and form.is_valid():
        updated = form.save(commit=False)
        updated.school = request.school
        updated.full_clean()
        updated.save()
        messages.success(request, "Instructional weekdays updated.")
        return redirect("attendance_calendar")
    return render(request, "attendance/calendar.html", {
        "form": form,
        "closures": SchoolClosure.objects.filter(school=request.school).select_related("term__academic_year"),
    })


@calendar_admin_required
def add_closure(request):
    form = SchoolClosureForm(request.POST or None, school=request.school)
    if request.method == "POST" and form.is_valid():
        closure = form.save(commit=False)
        closure.school = request.school
        closure.created_by = request.school_membership
        closure.full_clean()
        closure.save()
        messages.success(request, "School closure added.")
        return redirect("attendance_calendar")
    return render(request, "attendance/closure_form.html", {"form": form})
