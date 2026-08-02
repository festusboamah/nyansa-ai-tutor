from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, TeacherAssignment, Term
from courses.models import Subject
from .forms import AcademicYearForm, ClassEnrollmentForm, SchoolClassForm, SchoolInvitationForm, SchoolProfileForm, StudentRosterUploadForm, SubjectOfferingForm, SubjectSetupForm, TeacherAssignmentForm, TermForm
from .models import SchoolInvitation, SchoolMembership
from .roster_import import import_student_roster, parse_student_roster
from .curriculum import generate_ghana_curriculum
from .services import accept_invitation, create_invitation, has_school_role


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


ONBOARDING_STEPS = (
    ("profile", "School profile"),
    ("year", "Academic year"),
    ("term", "Term"),
    ("people", "Invite people"),
    ("class", "Classes"),
    ("subject", "Subjects"),
    ("offering", "Subject offerings"),
    ("assignment", "Assign teachers"),
    ("enrollment", "Enrol students"),
)


def _onboarding_state(school):
    active_roles = set(SchoolMembership.objects.filter(
        school=school,
        role__in=[SchoolMembership.Role.TEACHER, SchoolMembership.Role.STUDENT],
        status=SchoolMembership.Status.ACTIVE,
    ).values_list("role", flat=True))
    invited_roles = set(SchoolInvitation.objects.filter(
        school=school,
        role__in=[SchoolMembership.Role.TEACHER, SchoolMembership.Role.STUDENT],
        status=SchoolInvitation.Status.PENDING,
    ).values_list("role", flat=True))
    people_roles = active_roles | invited_roles
    return {
        "profile": bool(school.address and school.phone and school.email),
        "year": AcademicYear.objects.filter(school=school).exists(),
        "term": Term.objects.filter(academic_year__school=school).count() >= 3,
        "people": {
            SchoolMembership.Role.TEACHER,
            SchoolMembership.Role.STUDENT,
        }.issubset(people_roles),
        "class": SchoolClass.objects.filter(school=school).exists(),
        "subject": Subject.objects.filter(school=school).exists(),
        "offering": SubjectOffering.objects.filter(school=school).exists(),
        "assignment": TeacherAssignment.objects.filter(offering__school=school).exists(),
        "enrollment": ClassEnrollment.objects.filter(school_class__school=school).exists(),
    }


def _next_onboarding_step(state):
    return next((key for key, _ in ONBOARDING_STEPS if not state[key]), "complete")


def _step_after(current_step, state):
    """Advance in wizard order, keeping multi-entry people setup open until ready."""
    if current_step == "people" and not state["people"]:
        return "people"
    if current_step == "term" and not state["term"]:
        return "term"
    keys = [key for key, _ in ONBOARDING_STEPS]
    index = keys.index(current_step)
    return keys[index + 1] if index + 1 < len(keys) else "complete"


@admin_required
def school_onboarding(request):
    state = _onboarding_state(request.school)
    step_keys = {key for key, _ in ONBOARDING_STEPS} | {"complete"}
    step = request.POST.get("step") or request.GET.get("step") or _next_onboarding_step(state)
    if step not in step_keys:
        raise Http404

    if request.method == "POST" and request.POST.get("action") == "generate_curriculum":
        created_subjects, created_offerings, unmatched = generate_ghana_curriculum(school=request.school)
        if unmatched:
            messages.warning(
                request,
                "Curriculum generated, but these class names were not recognised: " + ", ".join(unmatched) + ".",
            )
        messages.success(
            request,
            f"Curriculum ready: {created_subjects} subject(s) and {created_offerings} class-term offering(s) created.",
        )
        return redirect(f"{reverse('school_onboarding')}?step=assignment")

    completed = sum(state.values())
    display_steps = [
        {"key": key, "label": label, "complete": state[key]}
        for key, label in ONBOARDING_STEPS
    ]
    if step == "complete":
        return render(request, "schools/onboarding.html", {
            "steps": display_steps,
            "state": state,
            "current_step": step,
            "completed": completed,
            "progress_percent": round(completed / len(ONBOARDING_STEPS) * 100),
        })

    form_classes = {
        "profile": SchoolProfileForm,
        "year": AcademicYearForm,
        "term": TermForm,
        "people": SchoolInvitationForm,
        "class": SchoolClassForm,
        "subject": SubjectSetupForm,
        "offering": SubjectOfferingForm,
        "assignment": TeacherAssignmentForm,
        "enrollment": ClassEnrollmentForm,
    }
    form_class = form_classes[step]
    kwargs = {"data": request.POST or None, "files": request.FILES or None}
    if step == "profile":
        kwargs["instance"] = request.school
    elif step not in {"people"}:
        kwargs["school"] = request.school
    form = form_class(**kwargs)

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                if step == "people":
                    invitation, token = create_invitation(
                        school=request.school,
                        email=form.cleaned_data["email"],
                        role=form.cleaned_data["role"],
                        invited_by=request.user,
                    )
                    invitation_url = request.build_absolute_uri(reverse("accept_school_invitation", args=[token]))
                    send_mail(
                        f"Invitation to join {request.school.name} on Nyansa",
                        f"You have been invited as {invitation.get_role_display()}. Accept here: {invitation_url}",
                        settings.DEFAULT_FROM_EMAIL,
                        [invitation.email],
                    )
                else:
                    obj = form.save(commit=False)
                    if step in {"year", "class", "subject", "offering"}:
                        obj.school = request.school
                    if step == "year" and obj.is_current:
                        AcademicYear.objects.filter(school=request.school, is_current=True).exclude(pk=obj.pk).update(is_current=False)
                    obj.full_clean()
                    obj.save()
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f"{dict(ONBOARDING_STEPS)[step]} saved. Continue with the next setup step.")
            updated_state = _onboarding_state(request.school)
            next_step = step if request.POST.get("save_action") == "add_another" else _step_after(step, updated_state)
            return redirect(f"{reverse('school_onboarding')}?step={next_step}")

    return render(request, "schools/onboarding.html", {
        "form": form,
        "steps": display_steps,
        "state": state,
        "current_step": step,
        "current_label": dict(ONBOARDING_STEPS)[step],
        "completed": completed,
        "progress_percent": round(completed / len(ONBOARDING_STEPS) * 100),
        "education_levels": request.school,
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


@admin_required
def people_directory(request):
    return render(request, "schools/people_directory.html", {
        "memberships": SchoolMembership.objects.filter(school=request.school).select_related("user"),
        "invitations": SchoolInvitation.objects.filter(school=request.school)[:25],
    })


@admin_required
def bulk_student_import(request):
    preview = request.session.get("student_roster_preview")
    if request.method == "POST" and request.POST.get("action") == "confirm":
        if not preview:
            messages.error(request, "Upload and preview a roster before confirming.")
            return redirect("bulk_student_import")
        school_class = SchoolClass.objects.filter(
            school=request.school, pk=preview.get("school_class_id")
        ).first()
        if not school_class:
            raise Http404
        created, updated = import_student_roster(school_class=school_class, records=preview["records"])
        request.session.pop("student_roster_preview", None)
        messages.success(request, f"Roster imported: {created} student(s) created and {updated} updated.")
        return redirect("people_directory")

    form = StudentRosterUploadForm(request.POST or None, request.FILES or None, school=request.school)
    errors = []
    if request.method == "POST" and form.is_valid():
        try:
            records, errors = parse_student_roster(form.cleaned_data["roster_file"])
        except (ValidationError, ValueError, OSError) as error:
            form.add_error("roster_file", error)
        else:
            if not errors:
                school_class = form.cleaned_data["school_class"]
                preview = {"school_class_id": school_class.id, "school_class_name": str(school_class), "records": records}
                request.session["student_roster_preview"] = preview
    return render(request, "schools/bulk_student_import.html", {"form": form, "preview": preview, "row_errors": errors})


@admin_required
def student_roster_template(request):
    response = HttpResponse(
        "student_id,first_name,last_name,gender,date_of_birth,guardian_name,guardian_phone\n"
        "STU-001,Ama,Mensah,Female,2014-05-12,Adwoa Mensah,0200000000\n",
        content_type="text/csv",
    )
    response["Content-Disposition"] = 'attachment; filename="nyansa-student-roster-template.csv"'
    return response


@admin_required
def invite_member(request):
    form = SchoolInvitationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        invitation, token = create_invitation(
            school=request.school,
            email=form.cleaned_data["email"],
            role=form.cleaned_data["role"],
            invited_by=request.user,
        )
        invitation_url = request.build_absolute_uri(reverse("accept_school_invitation", args=[token]))
        send_mail(
            f"Invitation to join {request.school.name} on Nyansa",
            f"You have been invited as {invitation.get_role_display()}. Accept here: {invitation_url}",
            settings.DEFAULT_FROM_EMAIL,
            [invitation.email],
        )
        messages.success(request, "Invitation sent.")
        return redirect("people_directory")
    return render(request, "schools/admin_form.html", {"form": form, "title": "Invite member"})


@admin_required
def set_membership_status(request, membership_id, status):
    if request.method != "POST":
        return redirect("people_directory")
    membership = SchoolMembership.objects.filter(school=request.school, id=membership_id).first()
    if not membership:
        raise Http404
    if membership.user_id == request.user.id:
        messages.error(request, "You cannot suspend your own administrator membership.")
        return redirect("people_directory")
    allowed = {SchoolMembership.Status.ACTIVE, SchoolMembership.Status.SUSPENDED}
    if status not in allowed:
        raise Http404
    membership.status = status
    membership.save(update_fields=["status", "updated_at"])
    messages.success(request, "Membership updated.")
    return redirect("people_directory")


@login_required
def accept_school_invitation(request, token):
    if request.method == "POST":
        accept_invitation(raw_token=token, user=request.user)
        messages.success(request, "School invitation accepted.")
        return redirect("home")
    return render(request, "schools/accept_invitation.html")
