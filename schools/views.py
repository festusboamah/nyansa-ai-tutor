from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db import models
from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, TeacherAssignment, Term
from courses.models import Subject
from .forms import AcademicYearForm, ClassEnrollmentForm, SchoolClassForm, SchoolInvitationForm, SchoolProfileForm, StaffInviteUploadForm, StudentRecordForm, StudentRosterUploadForm, SubjectOfferingForm, SubjectSetupForm, TeacherAssignmentForm, TermForm
from .models import School, SchoolInvitation, SchoolMembership
from .roster_import import import_student_roster, parse_student_roster
from .staff_import import import_staff_invitations, parse_staff_invite_list
from .curriculum import generate_ghana_curriculum, generate_school_classes
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
    classes = SchoolClass.objects.filter(school=school)
    if classes.exclude(name="Demo Class").exists():
        classes = classes.exclude(name="Demo Class")
    offerings = SubjectOffering.objects.filter(school=school)
    if offerings.exclude(school_class__name="Demo Class", term__name="Demo Term").exists():
        offerings = offerings.exclude(models.Q(school_class__name="Demo Class") | models.Q(term__name="Demo Term"))
    return render(request, "schools/admin_dashboard.html", {
        "school": school,
        "years": AcademicYear.objects.filter(school=school).prefetch_related("terms"),
        "classes": classes.select_related("academic_year", "class_teacher__user"),
        "offerings": offerings.select_related("school_class", "subject", "term"),
        "assignments": TeacherAssignment.objects.filter(offering__in=offerings).select_related("teacher__user", "offering__subject"),
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

GHANA_EDUCATION_SYSTEMS = (School.EducationSystem.BASIC, School.EducationSystem.SENIOR_HIGH)

# Ghana's GES mandates a 3-term year; other systems just need at least one
# term on record before the "term" onboarding step counts as complete.
MIN_TERMS_BY_EDUCATION_SYSTEM = {
    School.EducationSystem.BASIC: 3,
    School.EducationSystem.SENIOR_HIGH: 3,
    School.EducationSystem.CAMBRIDGE: 1,
    School.EducationSystem.TERTIARY: 1,
}


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
        "term": Term.objects.filter(academic_year__school=school).count()
        >= MIN_TERMS_BY_EDUCATION_SYSTEM[school.education_system],
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
    if request.school.education_system == School.EducationSystem.TERTIARY:
        return render(request, "schools/onboarding_tertiary_holding.html")

    state = _onboarding_state(request.school)
    step_keys = {key for key, _ in ONBOARDING_STEPS} | {"complete"}
    step = request.POST.get("step") or request.GET.get("step") or _next_onboarding_step(state)
    if step not in step_keys:
        raise Http404
    uses_ghana_curriculum = request.school.education_system in GHANA_EDUCATION_SYSTEMS

    if request.method == "POST" and request.POST.get("action") in {"generate_curriculum", "generate_classes"} and not uses_ghana_curriculum:
        return HttpResponse(status=400)

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

    if request.method == "POST" and request.POST.get("action") == "generate_classes":
        academic_year, created_count = generate_school_classes(school=request.school)
        if academic_year is None:
            messages.error(request, "Create an academic year before generating classes.")
            return redirect(f"{reverse('school_onboarding')}?step=year")
        created_subjects, created_offerings, unmatched = generate_ghana_curriculum(school=request.school)
        messages.success(
            request,
            f"Setup generated for {academic_year.name}: {created_count} class(es), "
            f"{created_subjects} subject(s), and {created_offerings} class-term offering(s).",
        )
        if unmatched:
            messages.warning(request, "These custom class names need manual offerings: " + ", ".join(unmatched) + ".")
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
        "generated_offering_count": SubjectOffering.objects.filter(school=request.school).count(),
        "uses_ghana_curriculum": uses_ghana_curriculum,
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
    return redirect("teacher_assignment_management")


@admin_required
@transaction.atomic
def teacher_assignment_management(request):
    form = TeacherAssignmentForm(request.POST or None, school=request.school)
    if request.method == "POST" and request.POST.get("action") == "assign" and form.is_valid():
        selected = form.cleaned_data["offering"]
        offerings = SubjectOffering.objects.filter(pk=selected.pk)
        if form.cleaned_data["apply_all_terms"]:
            offerings = SubjectOffering.objects.filter(
                school=request.school,
                school_class=selected.school_class,
                subject=selected.subject,
                term__academic_year=selected.term.academic_year,
            )
        created_count = 0
        for offering in offerings:
            if form.cleaned_data["is_lead"]:
                TeacherAssignment.objects.filter(offering=offering, is_lead=True).update(is_lead=False)
            _assignment, created = TeacherAssignment.objects.get_or_create(
                offering=offering,
                teacher=form.cleaned_data["teacher"],
                defaults={"is_lead": form.cleaned_data["is_lead"]},
            )
            created_count += int(created)
        if created_count:
            messages.success(request, f"Teacher assigned to {created_count} offering(s).")
        else:
            messages.info(request, "That teacher is already assigned to the selected offering(s).")
        return redirect("teacher_assignment_management")

    offerings = SubjectOffering.objects.filter(school=request.school)
    if offerings.exclude(school_class__name="Demo Class", term__name="Demo Term").exists():
        offerings = offerings.exclude(models.Q(school_class__name="Demo Class") | models.Q(term__name="Demo Term"))
    offerings = offerings.select_related(
        "school_class__academic_year", "subject", "term__academic_year"
    )
    filters = {
        "year": request.GET.get("year", ""), "term": request.GET.get("term", ""),
        "class": request.GET.get("class", ""), "subject": request.GET.get("subject", ""),
        "teacher": request.GET.get("teacher", ""),
    }
    assignments = TeacherAssignment.objects.filter(offering__in=offerings).select_related(
        "teacher__user", "offering__school_class__academic_year", "offering__subject", "offering__term"
    )
    for key, lookup in {
        "year": "offering__term__academic_year_id", "term": "offering__term_id",
        "class": "offering__school_class_id", "subject": "offering__subject_id", "teacher": "teacher_id",
    }.items():
        if filters[key].isdigit():
            assignments = assignments.filter(**{lookup: filters[key]})
    assignments = assignments.order_by(
        "offering__school_class__name", "offering__subject__name", "offering__term__order", "teacher__user__last_name"
    )
    teachers = SchoolMembership.objects.filter(
        school=request.school, role=SchoolMembership.Role.TEACHER, status=SchoolMembership.Status.ACTIVE
    ).select_related("user")
    unassigned = offerings.filter(teacher_assignments__isnull=True).order_by(
        "school_class__name", "subject__name", "term__order"
    )
    return render(request, "schools/teacher_assignments.html", {
        "form": form, "assignments": assignments, "unassigned": unassigned[:20],
        "unassigned_count": unassigned.count(), "filters": filters, "teachers": teachers,
        "years": AcademicYear.objects.filter(school=request.school),
        "terms": Term.objects.filter(academic_year__school=request.school).exclude(name="Demo Term").select_related("academic_year"),
        "classes": SchoolClass.objects.filter(school=request.school).exclude(name="Demo Class").select_related("academic_year"),
        "subjects": Subject.objects.filter(school=request.school),
    })


@admin_required
@transaction.atomic
def update_teacher_assignment(request, assignment_id):
    if request.method != "POST":
        return redirect("teacher_assignment_management")
    assignment = TeacherAssignment.objects.filter(
        pk=assignment_id, offering__school=request.school
    ).select_related("offering", "teacher").first()
    teacher = SchoolMembership.objects.filter(
        pk=request.POST.get("teacher"), school=request.school,
        role=SchoolMembership.Role.TEACHER, status=SchoolMembership.Status.ACTIVE,
    ).first()
    if not assignment or not teacher:
        raise Http404
    is_lead = request.POST.get("is_lead") == "on"
    if is_lead:
        TeacherAssignment.objects.filter(offering=assignment.offering, is_lead=True).exclude(pk=assignment.pk).update(is_lead=False)
    if assignment.teacher_id != teacher.id:
        offering = assignment.offering
        assignment.delete()
        replacement, created = TeacherAssignment.objects.get_or_create(
            offering=offering, teacher=teacher, defaults={"is_lead": is_lead}
        )
        if not created and replacement.is_lead != is_lead:
            replacement.is_lead = is_lead
            replacement.save(update_fields=["is_lead"])
        messages.success(request, "Teacher assignment replaced.")
    else:
        assignment.is_lead = is_lead
        assignment.save(update_fields=["is_lead"])
        messages.success(request, "Teacher assignment updated.")
    return redirect("teacher_assignment_management")


@admin_required
def delete_teacher_assignment(request, assignment_id):
    if request.method != "POST":
        return redirect("teacher_assignment_management")
    assignment = TeacherAssignment.objects.filter(pk=assignment_id, offering__school=request.school).first()
    if not assignment:
        raise Http404
    assignment.delete()
    messages.success(request, "Teacher assignment removed.")
    return redirect("teacher_assignment_management")


@admin_required
def people_directory(request):
    classes = SchoolClass.objects.filter(school=request.school)
    if classes.exclude(name="Demo Class").exists():
        classes = classes.exclude(name="Demo Class")
    return render(request, "schools/people_directory.html", {
        "memberships": SchoolMembership.objects.filter(school=request.school).select_related("user"),
        "invitations": SchoolInvitation.objects.filter(school=request.school)[:25],
        "classes": classes.select_related("academic_year").annotate(
            active_student_count=models.Count(
                "student_enrollments",
                filter=models.Q(student_enrollments__status=ClassEnrollment.Status.ACTIVE),
            )
        ),
    })


def _school_class_or_404(request, class_id):
    school_class = SchoolClass.objects.filter(
        school=request.school, pk=class_id
    ).select_related("academic_year", "class_teacher__user").first()
    if not school_class:
        raise Http404
    return school_class


@admin_required
def class_roster(request, class_id):
    school_class = _school_class_or_404(request, class_id)
    enrollments = ClassEnrollment.objects.filter(
        school_class=school_class, status=ClassEnrollment.Status.ACTIVE
    ).select_related("student__user", "student__student_profile").order_by(
        "student__user__last_name", "student__user__first_name", "student__identifier"
    )
    transfer_classes = SchoolClass.objects.filter(school=request.school).exclude(pk=school_class.pk).select_related("academic_year")
    promotion_classes = transfer_classes.filter(academic_year__start_date__gt=school_class.academic_year.start_date)
    return render(request, "schools/class_roster.html", {
        "school_class": school_class,
        "enrollments": enrollments,
        "transfer_classes": transfer_classes,
        "promotion_classes": promotion_classes,
    })


@admin_required
def edit_student_record(request, membership_id):
    membership = SchoolMembership.objects.filter(
        school=request.school, pk=membership_id, role=SchoolMembership.Role.STUDENT
    ).select_related("user").first()
    if not membership:
        raise Http404
    form = StudentRecordForm(request.POST or None, membership=membership)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Student record updated.")
        class_id = request.POST.get("return_class")
        if class_id and SchoolClass.objects.filter(school=request.school, pk=class_id).exists():
            return redirect("class_roster", class_id=class_id)
        return redirect("people_directory")
    return render(request, "schools/student_record_form.html", {"form": form, "membership": membership})


@admin_required
@transaction.atomic
def transfer_student(request, class_id, enrollment_id):
    if request.method != "POST":
        return redirect("class_roster", class_id=class_id)
    source = _school_class_or_404(request, class_id)
    enrollment = ClassEnrollment.objects.filter(
        pk=enrollment_id, school_class=source, status=ClassEnrollment.Status.ACTIVE
    ).select_related("student").first()
    target = SchoolClass.objects.filter(school=request.school, pk=request.POST.get("target_class")).first()
    if not enrollment or not target or target.pk == source.pk:
        raise Http404
    enrollment.status = ClassEnrollment.Status.TRANSFERRED
    enrollment.save(update_fields=["status"])
    target_enrollment, _ = ClassEnrollment.objects.get_or_create(
        school_class=target, student=enrollment.student,
        defaults={"status": ClassEnrollment.Status.ACTIVE},
    )
    if target_enrollment.status != ClassEnrollment.Status.ACTIVE:
        target_enrollment.status = ClassEnrollment.Status.ACTIVE
        target_enrollment.save(update_fields=["status"])
    messages.success(request, f"Student moved to {target.name}.")
    return redirect("class_roster", class_id=source.pk)


@admin_required
@transaction.atomic
def promote_class(request, class_id):
    if request.method != "POST":
        return redirect("class_roster", class_id=class_id)
    source = _school_class_or_404(request, class_id)
    target = SchoolClass.objects.filter(
        school=request.school,
        pk=request.POST.get("target_class"),
        academic_year__start_date__gt=source.academic_year.start_date,
    ).first()
    if not target:
        messages.error(request, "Choose a class in a later academic year.")
        return redirect("class_roster", class_id=source.pk)
    active = list(ClassEnrollment.objects.filter(school_class=source, status=ClassEnrollment.Status.ACTIVE))
    for enrollment in active:
        ClassEnrollment.objects.update_or_create(
            school_class=target, student=enrollment.student,
            defaults={"status": ClassEnrollment.Status.ACTIVE},
        )
    ClassEnrollment.objects.filter(pk__in=[item.pk for item in active]).update(status=ClassEnrollment.Status.COMPLETED)
    messages.success(request, f"{len(active)} student(s) promoted to {target.name}.")
    return redirect("class_roster", class_id=target.pk)


@admin_required
def export_class_roster(request, class_id):
    import csv
    school_class = _school_class_or_404(request, class_id)
    response = HttpResponse(content_type="text/csv")
    safe_name = "-".join(school_class.name.lower().split())
    response["Content-Disposition"] = f'attachment; filename="{safe_name}-roster.csv"'
    writer = csv.writer(response)
    writer.writerow(["student_id", "first_name", "last_name", "gender", "date_of_birth", "guardian_name", "guardian_phone"])
    enrollments = ClassEnrollment.objects.filter(
        school_class=school_class, status=ClassEnrollment.Status.ACTIVE
    ).select_related("student__user", "student__student_profile")
    for enrollment in enrollments:
        student, user = enrollment.student, enrollment.student.user
        profile = getattr(student, "student_profile", None)
        writer.writerow([
            student.identifier, user.first_name, user.last_name,
            profile.get_gender_display() if profile else "",
            profile.date_of_birth.isoformat() if profile and profile.date_of_birth else "",
            profile.guardian_name if profile else "", profile.guardian_phone if profile else "",
        ])
    return response


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
def bulk_staff_import(request):
    preview = request.session.get("staff_invite_preview")
    if request.method == "POST" and request.POST.get("action") == "confirm":
        if not preview:
            messages.error(request, "Upload and preview a file before confirming.")
            return redirect("bulk_staff_import")
        results = import_staff_invitations(
            school=request.school, records=preview["records"], invited_by=request.user, request=request,
        )
        request.session.pop("staff_invite_preview", None)
        invited = sum(1 for r in results if r["status"] == "invited")
        skipped = len(results) - invited
        messages.success(
            request,
            f"{invited} invitation(s) sent." + (f" {skipped} row(s) skipped (already invited/a member, or failed)." if skipped else ""),
        )
        return redirect("people_directory")

    form = StaffInviteUploadForm(request.POST or None, request.FILES or None)
    errors = []
    if request.method == "POST" and form.is_valid():
        try:
            records, errors = parse_staff_invite_list(form.cleaned_data["invite_file"])
        except (ValidationError, ValueError, OSError) as error:
            form.add_error("invite_file", error)
        else:
            if not errors:
                preview = {"records": records}
                request.session["staff_invite_preview"] = preview
    return render(request, "schools/bulk_staff_import.html", {
        "form": form, "preview": preview, "row_errors": errors,
        "role_choices": SchoolMembership.Role.choices,
    })


@admin_required
def staff_invite_template(request):
    response = HttpResponse(
        "email,role\n"
        "ama.mensah@example.com,TEACHER\n"
        "kwame.owusu@example.com,PARENT\n",
        content_type="text/csv",
    )
    response["Content-Disposition"] = 'attachment; filename="nyansa-staff-invite-template.csv"'
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
