from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from academics.models import AcademicYear, SchoolClass, SubjectOffering, TeacherAssignment, Term
from .forms import AcademicYearForm, SchoolClassForm, SubjectOfferingForm, TeacherAssignmentForm, TermForm
from .models import SchoolMembership
from .services import has_school_role


def admin_required(view):
    @login_required
    def wrapped(request, *args, **kwargs):
        if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
            messages.error(request, "This page is only available to school administrators.")
            return redirect("home")
        return view(request, *args, **kwargs)
    return wrapped


@admin_required
def school_admin_dashboard(request):
    school = request.school
    return render(request, "schools/admin_dashboard.html", {
        "school": school,
        "years": AcademicYear.objects.filter(school=school).prefetch_related("terms"),
        "classes": SchoolClass.objects.filter(school=school).select_related("academic_year", "class_teacher__user"),
        "offerings": SubjectOffering.objects.filter(school=school).select_related("school_class", "subject", "term"),
        "assignments": TeacherAssignment.objects.filter(offering__school=school).select_related("teacher__user", "offering__subject"),
        "member_count": SchoolMembership.objects.filter(school=school).count(),
    })


def _create(request, form_class, title, success_message, prepare):
    form = form_class(request.POST or None, school=request.school)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        prepare(obj, request.school)
        obj.full_clean()
        obj.save()
        messages.success(request, success_message)
        return redirect("school_admin_dashboard")
    return render(request, "schools/admin_form.html", {"form": form, "title": title})


@admin_required
def create_academic_year(request):
    return _create(request, AcademicYearForm, "Add academic year", "Academic year added.", lambda obj, school: setattr(obj, "school", school))


@admin_required
def create_term(request):
    return _create(request, TermForm, "Add term", "Term added.", lambda obj, school: None)


@admin_required
def create_school_class(request):
    return _create(request, SchoolClassForm, "Add class", "Class added.", lambda obj, school: setattr(obj, "school", school))


@admin_required
def create_subject_offering(request):
    return _create(request, SubjectOfferingForm, "Add subject offering", "Subject offering added.", lambda obj, school: setattr(obj, "school", school))


@admin_required
def create_teacher_assignment(request):
    return _create(request, TeacherAssignmentForm, "Assign teacher", "Teacher assigned.", lambda obj, school: None)
