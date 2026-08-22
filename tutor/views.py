from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.dateparse import parse_date

from courses.models import Material, Subject, StudyDocument
from mastery.models import Topic
from schools.models import SchoolMembership
from schools.services import has_school_role

from . import engine
from .models import DIFFICULTY_ORDER, DifficultyLevel, TutorSession, TutorMode, TutorSettings


def available_modes(school):
    settings_row = TutorSettings.objects.filter(school=school).first()
    disabled = set(settings_row.disabled_modes) if settings_row else set()
    return [(value, label) for value, label in TutorMode.choices if value not in disabled]


@login_required
def tutor_home_view(request):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "The AI tutor is only available to students.")
        return redirect("home")

    sessions = TutorSession.objects.filter(
        student=request.user, school=request.school
    ).select_related("subject")
    subjects = Subject.objects.filter(school=request.school)
    documents = StudyDocument.objects.filter(student=request.user, school=request.school)
    materials = Material.objects.filter(
        subject__school=request.school, subject__enrollments__student=request.user,
        material_type=Material.MaterialType.DOCUMENT,
    ).exclude(file="").distinct()
    topics = Topic.objects.filter(
        strand__subject__school=request.school, strand__subject__enrollments__student=request.user,
    ).select_related("strand__subject")

    return render(request, "tutor/home.html", {
        "sessions": sessions,
        "subjects": subjects,
        "documents": documents,
        "materials": materials,
        "topics": topics,
        "modes": available_modes(request.school),
    })


@login_required
def start_session_view(request):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "The AI tutor is only available to students.")
        return redirect("home")

    if request.method != "POST":
        return redirect("tutor_home")

    mode = request.POST.get("mode")
    allowed_modes = {value for value, _ in available_modes(request.school)}
    if mode not in allowed_modes:
        messages.error(request, "Please choose a valid tutor mode.")
        return redirect("tutor_home")

    subject = None
    subject_id = request.POST.get("subject_id")
    if subject_id:
        subject = get_object_or_404(Subject, id=subject_id, school=request.school)

    study_document = None
    document_id = request.POST.get("document_id")
    if document_id:
        study_document = get_object_or_404(
            StudyDocument, id=document_id, student=request.user, school=request.school
        )

    material = None
    material_id = request.POST.get("material_id")
    if material_id:
        material = get_object_or_404(
            Material, id=material_id, subject__school=request.school,
            subject__enrollments__student=request.user,
        )

    topic = None
    topic_id = request.POST.get("topic_id")
    if topic_id:
        topic = get_object_or_404(
            Topic, id=topic_id, strand__subject__school=request.school,
            strand__subject__enrollments__student=request.user,
        )

    session = TutorSession.objects.create(
        school=request.school,
        student=request.user,
        mode=mode,
        subject=subject,
        study_document=study_document,
        material=material,
        topic=topic,
        title=f"{TutorMode(mode).label}" + (f" - {subject.name}" if subject else ""),
    )
    return redirect("tutor_session_detail", session_id=session.id)


@login_required
def session_detail_view(request, session_id):
    session = get_object_or_404(
        TutorSession, id=session_id, student=request.user, school=request.school
    )

    if request.method == "POST":
        student_text = request.POST.get("message", "").strip()
        if student_text:
            engine.send_message(session, student_text)
        return redirect("tutor_session_detail", session_id=session.id)

    return render(request, "tutor/session_detail.html", {
        "session": session,
        "conversation": session.messages.all(),
    })


@login_required
def tutor_settings_view(request):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied

    settings_row, _ = TutorSettings.objects.get_or_create(school=request.school)

    if request.method == "POST":
        disabled = [value for value, _ in TutorMode.choices if request.POST.get(f"enabled_{value}") != "on"]
        settings_row.disabled_modes = disabled
        hint_depth_raw = request.POST.get("max_hint_depth", "").strip()
        if hint_depth_raw:
            try:
                settings_row.max_hint_depth = max(1, int(hint_depth_raw))
            except ValueError:
                messages.error(request, "Max hint depth must be a whole number.")
                return redirect("tutor_settings")
        settings_row.allow_final_answer_reveal = request.POST.get("allow_final_answer_reveal") == "on"
        if "daily_usage_limit" in request.POST:
            usage_limit_raw = request.POST.get("daily_usage_limit", "").strip()
            if usage_limit_raw:
                try:
                    settings_row.daily_usage_limit = max(1, int(usage_limit_raw))
                except ValueError:
                    messages.error(request, "Daily usage limit must be a whole number.")
                    return redirect("tutor_settings")
            else:
                settings_row.daily_usage_limit = None

        min_difficulty = request.POST.get("min_difficulty", settings_row.min_difficulty)
        max_difficulty = request.POST.get("max_difficulty", settings_row.max_difficulty)
        if min_difficulty not in DifficultyLevel.values or max_difficulty not in DifficultyLevel.values:
            messages.error(request, "Please choose a valid difficulty range.")
            return redirect("tutor_settings")
        if DIFFICULTY_ORDER.index(min_difficulty) > DIFFICULTY_ORDER.index(max_difficulty):
            messages.error(request, "Minimum difficulty cannot be harder than maximum difficulty.")
            return redirect("tutor_settings")
        settings_row.min_difficulty = min_difficulty
        settings_row.max_difficulty = max_difficulty

        if "restricted_period_start" in request.POST or "restricted_period_end" in request.POST:
            start_raw = request.POST.get("restricted_period_start", "").strip()
            end_raw = request.POST.get("restricted_period_end", "").strip()

            if start_raw and not parse_date(start_raw):
                messages.error(request, "Assessment period start date is invalid.")
                return redirect("tutor_settings")
            if end_raw and not parse_date(end_raw):
                messages.error(request, "Assessment period end date is invalid.")
                return redirect("tutor_settings")

            start_date = parse_date(start_raw) if start_raw else None
            end_date = parse_date(end_raw) if end_raw else None

            if bool(start_date) != bool(end_date):
                messages.error(request, "Please provide both a start and end date, or leave both blank.")
                return redirect("tutor_settings")
            if start_date and end_date and start_date > end_date:
                messages.error(request, "Assessment period start date must be before the end date.")
                return redirect("tutor_settings")

            settings_row.restricted_period_start = start_date
            settings_row.restricted_period_end = end_date

        settings_row.full_clean()
        settings_row.save(update_fields=[
            "disabled_modes", "max_hint_depth", "allow_final_answer_reveal", "daily_usage_limit",
            "min_difficulty", "max_difficulty", "restricted_period_start", "restricted_period_end",
        ])
        messages.success(request, "Tutor settings saved.")
        return redirect("tutor_settings")

    return render(request, "tutor/settings.html", {
        "modes": TutorMode.choices,
        "disabled_modes": set(settings_row.disabled_modes),
        "settings_row": settings_row,
        "difficulty_choices": DifficultyLevel.choices,
    })
