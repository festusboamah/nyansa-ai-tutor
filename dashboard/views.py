from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from courses.models import Subject, Enrollment
from quizzes.models import Quiz, Submission
from accounts.models import User
from .ai_reports import generate_student_report
from .models import LessonNote, SchemeOfLearning, StudentNote
from .forms import LessonNoteForm, SchemeOfLearningForm, StudentNoteForm
from .forms import LessonCommentForm, LessonNoteRevisionForm
from .lesson_ai import generate_demo_lesson_note, generate_lesson_note
from .lesson_docx import build_lesson_note_docx
from .scheme_ai import generate_demo_scheme, generate_scheme_of_learning
from .scheme_docx import build_scheme_of_learning_docx
from .student_notes_ai import generate_demo_student_note, generate_student_notes
from .student_note_docx import build_student_note_docx
from .personal_school_gate import generation_allowed, redirect_to_subscribe
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa
import markdown as md
from .email_utils import send_report_email
from schools.models import SchoolMembership
from schools.services import has_school_role
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from .lesson_workflow import (
    add_lesson_comment,
    record_initial_lesson_version,
    revise_lesson_note,
    review_lesson_note,
    submit_lesson_note,
)
from .models import LessonNoteNotification


@login_required
def teacher_dashboard_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "This page is only available to teachers.")
        return redirect("home")

    subjects = Subject.objects.filter(
        school=request.school, materials__teacher=request.user
    ).distinct()
    if not subjects.exists():
        subjects = Subject.objects.filter(
            school=request.school, quizzes__teacher=request.user
        ).distinct()

    subject_data = []
    for subject in subjects:
        enrollments = Enrollment.objects.filter(subject=subject).select_related("student")
        subject_data.append({
            "subject": subject,
            "student_count": enrollments.count(),
            "enrollments": enrollments,
        })

    from quizzes.models import Assignment
    assignments = Assignment.objects.filter(
        teacher=request.user, subject__school=request.school
    ).select_related("subject").order_by("-created_at")

    return render(request, "dashboard/teacher_dashboard.html", {
        "subject_data": subject_data,
        "assignments": assignments,
    })


@login_required
def student_report_view(request, student_id, subject_id):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "This page is only available to teachers.")
        return redirect("home")

    student = get_object_or_404(User, id=student_id)
    subject = get_object_or_404(Subject, id=subject_id, school=request.school)

    if not Enrollment.objects.filter(student=student, subject=subject).exists():
        messages.error(request, "This student is not enrolled in this subject.")
        return redirect("teacher_dashboard")

    submissions = Submission.objects.filter(
        student=student, quiz__subject=subject
    ).select_related("quiz").prefetch_related("answers")

    report_text = generate_student_report(student, subject, submissions)

    return render(request, "dashboard/student_report.html", {
        "student": student,
        "subject": subject,
        "submissions": submissions,
        "report_text": report_text,
    })

@login_required
def create_content_view(request):
    """Landing menu: pick which kind of document to generate before the
    type-specific form appears."""
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "This feature is only available to teachers.")
        return redirect("home")
    has_subject = Subject.objects.filter(school=request.school).exists()
    return render(request, "dashboard/create_content.html", {"has_subject": has_subject})


@login_required
def lesson_notes_list_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "This feature is only available to teachers.")
        return redirect("home")

    notes = LessonNote.objects.filter(
        teacher=request.user, subject__school=request.school
    ).order_by("-created_at")
    return render(request, "dashboard/lesson_notes_list.html", {"notes": notes})


@login_required
def create_lesson_note_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "This feature is only available to teachers.")
        return redirect("home")

    if request.method == "POST":
        if not generation_allowed(request):
            messages.warning(request, "You've used your 3 free generations - subscribe to keep going.")
            return redirect_to_subscribe(request)
        form = LessonNoteForm(request.POST, school=request.school)
        if form.is_valid():
            lesson_note = form.save(commit=False)
            lesson_note.teacher = request.user
            lesson_note.save()

            result = generate_lesson_note(
                class_level=lesson_note.class_level,
                subject_name=lesson_note.subject.name,
                week_ending=lesson_note.week_ending,
                strand_topic=lesson_note.strand_topic,
                content_standard=lesson_note.content_standard,
                learning_indicator=lesson_note.learning_indicator,
                performance_indicator=lesson_note.performance_indicator,
                reference=lesson_note.reference,
                resources=lesson_note.resources,
                num_days=lesson_note.num_days,
                sub_strand=lesson_note.sub_strand,
                core_competencies=lesson_note.core_competencies,
                school=request.school,
            )

            used_demo_fallback = False
            if result is None and settings.NYANSA_DEMO_MODE:
                result = generate_demo_lesson_note(
                    class_level=lesson_note.class_level,
                    subject_name=lesson_note.subject.name,
                    week_ending=lesson_note.week_ending,
                    strand_topic=lesson_note.strand_topic,
                    content_standard=lesson_note.content_standard,
                    learning_indicator=lesson_note.learning_indicator,
                    performance_indicator=lesson_note.performance_indicator,
                    reference=lesson_note.reference,
                    resources=lesson_note.resources,
                    num_days=lesson_note.num_days,
                )
                used_demo_fallback = True

            if result is None:
                messages.error(request, "AI generation is unavailable. Ask an administrator to configure the AI provider.")
                lesson_note.delete()
                return redirect("create_lesson_note")

            import json
            lesson_note.generated_content = json.dumps(result)
            if not lesson_note.content_standard:
                lesson_note.content_standard = result.get("content_standard", "")
            if not lesson_note.learning_indicator:
                lesson_note.learning_indicator = result.get("learning_indicator", "")
            if not lesson_note.performance_indicator:
                lesson_note.performance_indicator = result.get("performance_indicators", "")
            if not lesson_note.core_competencies:
                lesson_note.core_competencies = result.get("core_competencies", "")
            if not lesson_note.resources:
                lesson_note.resources = result.get("resources", "")
            lesson_note.save()
            record_initial_lesson_version(note=lesson_note, actor=request.school_membership)

            if used_demo_fallback:
                messages.warning(request, "Demo lesson template created without an external AI call. Review and edit it before submission.")
            else:
                messages.success(request, "Lesson note generated successfully!")
            return redirect("lesson_note_detail", note_id=lesson_note.id)
    else:
        form = LessonNoteForm(school=request.school)

    return render(request, "dashboard/create_lesson_note.html", {"form": form})


@login_required
def schemes_of_learning_list_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "This feature is only available to teachers.")
        return redirect("home")

    schemes = SchemeOfLearning.objects.filter(
        teacher=request.user, subject__school=request.school
    ).order_by("-created_at")
    return render(request, "dashboard/schemes_of_learning_list.html", {"schemes": schemes})


@login_required
def create_scheme_of_learning_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "This feature is only available to teachers.")
        return redirect("home")

    if request.method == "POST":
        if not generation_allowed(request):
            messages.warning(request, "You've used your 3 free generations - subscribe to keep going.")
            return redirect_to_subscribe(request)
        form = SchemeOfLearningForm(request.POST, school=request.school)
        if form.is_valid():
            scheme = form.save(commit=False)
            scheme.teacher = request.user
            scheme.save()

            result = generate_scheme_of_learning(
                class_level=scheme.class_level,
                subject_name=scheme.subject.name,
                term=scheme.term,
                num_weeks=scheme.num_weeks,
                starting_topics=form.cleaned_data.get("starting_topics", ""),
                school=request.school,
            )

            used_demo_fallback = False
            if result is None and settings.NYANSA_DEMO_MODE:
                result = generate_demo_scheme(
                    class_level=scheme.class_level, subject_name=scheme.subject.name,
                    term=scheme.term, num_weeks=scheme.num_weeks,
                )
                used_demo_fallback = True

            if result is None:
                messages.error(request, "AI generation is unavailable. Ask an administrator to configure the AI provider.")
                scheme.delete()
                return redirect("create_scheme_of_learning")

            import json
            scheme.generated_content = json.dumps(result)
            scheme.save()

            if used_demo_fallback:
                messages.warning(request, "Demo scheme created without an external AI call. Review it before use.")
            else:
                messages.success(request, "Scheme of learning generated successfully!")
            return redirect("scheme_of_learning_detail", scheme_id=scheme.id)
    else:
        form = SchemeOfLearningForm(school=request.school)

    return render(request, "dashboard/create_scheme_of_learning.html", {"form": form})


@login_required
def scheme_of_learning_detail_view(request, scheme_id):
    scheme = get_object_or_404(
        SchemeOfLearning, id=scheme_id, teacher=request.user, subject__school=request.school
    )
    import json
    try:
        scheme_data = json.loads(scheme.generated_content)
    except (json.JSONDecodeError, TypeError):
        scheme_data = None
    return render(request, "dashboard/scheme_of_learning_detail.html", {
        "scheme": scheme, "scheme_data": scheme_data,
    })


@login_required
def download_scheme_of_learning_docx(request, scheme_id):
    scheme = get_object_or_404(
        SchemeOfLearning, id=scheme_id, teacher=request.user, subject__school=request.school
    )
    import json
    try:
        scheme_data = json.loads(scheme.generated_content)
    except (json.JSONDecodeError, TypeError):
        scheme_data = None

    buffer = build_scheme_of_learning_docx(scheme, scheme_data)
    response = HttpResponse(
        buffer.read(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="{scheme.subject.name}_scheme_of_learning.docx"'
    return response


@login_required
def student_notes_list_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "This feature is only available to teachers.")
        return redirect("home")

    notes = StudentNote.objects.filter(
        teacher=request.user, subject__school=request.school
    ).order_by("-created_at")
    return render(request, "dashboard/student_notes_list.html", {"notes": notes})


@login_required
def create_student_note_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "This feature is only available to teachers.")
        return redirect("home")

    if request.method == "POST":
        if not generation_allowed(request):
            messages.warning(request, "You've used your 3 free generations - subscribe to keep going.")
            return redirect_to_subscribe(request)
        form = StudentNoteForm(request.POST, school=request.school)
        if form.is_valid():
            note = form.save(commit=False)
            note.teacher = request.user
            note.save()

            result = generate_student_notes(
                class_level=note.class_level,
                subject_name=note.subject.name,
                topic=note.topic,
                school=request.school,
            )

            used_demo_fallback = False
            if result is None and settings.NYANSA_DEMO_MODE:
                result = generate_demo_student_note(
                    class_level=note.class_level, subject_name=note.subject.name, topic=note.topic,
                )
                used_demo_fallback = True

            if result is None:
                messages.error(request, "AI generation is unavailable. Ask an administrator to configure the AI provider.")
                note.delete()
                return redirect("create_student_note")

            import json
            note.generated_content = json.dumps(result)
            note.save()

            if used_demo_fallback:
                messages.warning(request, "Demo student notes created without an external AI call. Review them before use.")
            else:
                messages.success(request, "Student notes generated successfully!")
            return redirect("student_note_detail", note_id=note.id)
    else:
        form = StudentNoteForm(school=request.school)

    return render(request, "dashboard/create_student_note.html", {"form": form})


@login_required
def student_note_detail_view(request, note_id):
    note = get_object_or_404(
        StudentNote, id=note_id, teacher=request.user, subject__school=request.school
    )
    import json
    try:
        note_data = json.loads(note.generated_content)
    except (json.JSONDecodeError, TypeError):
        note_data = None
    return render(request, "dashboard/student_note_detail.html", {"note": note, "note_data": note_data})


@login_required
def download_student_note_docx(request, note_id):
    note = get_object_or_404(
        StudentNote, id=note_id, teacher=request.user, subject__school=request.school
    )
    import json
    try:
        note_data = json.loads(note.generated_content)
    except (json.JSONDecodeError, TypeError):
        note_data = None

    buffer = build_student_note_docx(note, note_data)
    response = HttpResponse(
        buffer.read(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="{note.topic}_student_notes.docx"'
    return response


@login_required
def lesson_note_detail_view(request, note_id):
    note = get_object_or_404(
        LessonNote, id=note_id, teacher=request.user, subject__school=request.school
    )
    import json
    try:
        lesson_data = json.loads(note.generated_content)
    except (json.JSONDecodeError, TypeError):
        lesson_data = None
    return render(request, "dashboard/lesson_note_detail.html", {
        "note": note,
        "lesson_data": lesson_data,
        "events": note.events.select_related("actor__user"),
        "versions": note.versions.select_related("created_by__user"),
        "comment_form": LessonCommentForm(),
    })


@login_required
def edit_lesson_note_view(request, note_id):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "This feature is only available to teachers.")
        return redirect("home")
    note = get_object_or_404(
        LessonNote, pk=note_id, teacher=request.user, subject__school=request.school
    )
    if note.status not in {LessonNote.Status.DRAFT, LessonNote.Status.SENT_BACK}:
        messages.error(request, "Only draft or returned lesson notes can be revised.")
        return redirect("lesson_note_detail", note_id=note.pk)
    form = LessonNoteRevisionForm(request.POST or None, instance=note, school=request.school)
    if request.method == "POST" and form.is_valid():
        import json
        values = {field: form.cleaned_data[field] for field in LessonNoteForm.Meta.fields}
        values["generated_content"] = json.dumps(form.cleaned_data["generated_content"])
        try:
            revise_lesson_note(
                note=note,
                actor=request.school_membership,
                values=values,
                reason=form.cleaned_data["revision_reason"],
            )
        except (ValidationError, PermissionDenied) as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Lesson note revision saved.")
            return redirect("lesson_note_detail", note_id=note.pk)
    return render(request, "dashboard/edit_lesson_note.html", {"note": note, "form": form})


@login_required
def submit_lesson_note_view(request, note_id):
    note = get_object_or_404(
        LessonNote, pk=note_id, teacher=request.user, subject__school=request.school
    )
    if request.method == "POST":
        try:
            submit_lesson_note(
                note=note,
                actor=request.school_membership,
                message=request.POST.get("message", ""),
            )
        except (ValidationError, PermissionDenied) as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Lesson note submitted for review.")
    return redirect("lesson_note_detail", note_id=note.pk)


@login_required
def comment_lesson_note_view(request, note_id):
    note = get_object_or_404(LessonNote, pk=note_id, subject__school=request.school)
    if request.method == "POST":
        form = LessonCommentForm(request.POST)
        if form.is_valid():
            try:
                add_lesson_comment(
                    note=note, actor=request.school_membership, message=form.cleaned_data["message"]
                )
            except (ValidationError, PermissionDenied) as error:
                messages.error(request, str(error))
            else:
                messages.success(request, "Comment added.")
    if has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        return redirect("lesson_review_detail", note_id=note.pk)
    return redirect("lesson_note_detail", note_id=note.pk)


@login_required
def lesson_review_queue_view(request):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        messages.error(request, "This page is only available to school administrators.")
        return redirect("home")
    notes = LessonNote.objects.filter(
        subject__school=request.school,
        status__in=[LessonNote.Status.PENDING_REVIEW, LessonNote.Status.APPROVED],
    ).select_related("teacher", "subject", "reviewed_by__user")
    return render(request, "dashboard/lesson_review_queue.html", {"notes": notes})


@login_required
def lesson_review_detail_view(request, note_id):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        messages.error(request, "This page is only available to school administrators.")
        return redirect("home")
    note = get_object_or_404(
        LessonNote.objects.select_related("teacher", "subject").prefetch_related(
            "events__actor__user", "versions__created_by__user"
        ),
        pk=note_id,
        subject__school=request.school,
    )
    import json
    try:
        lesson_data = json.loads(note.generated_content)
    except (json.JSONDecodeError, TypeError):
        lesson_data = None
    return render(request, "dashboard/lesson_review_detail.html", {
        "note": note,
        "lesson_data": lesson_data,
        "events": note.events.all(),
        "versions": note.versions.all(),
        "comment_form": LessonCommentForm(),
    })


@login_required
def review_lesson_note_view(request, note_id):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        messages.error(request, "This page is only available to school administrators.")
        return redirect("home")
    note = get_object_or_404(LessonNote, pk=note_id, subject__school=request.school)
    if request.method == "POST":
        try:
            review_lesson_note(
                note=note,
                actor=request.school_membership,
                action=request.POST.get("action", ""),
                message=request.POST.get("message", ""),
            )
        except (ValidationError, PermissionDenied) as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Lesson-note review recorded.")
    return redirect("lesson_review_detail", note_id=note.pk)


@login_required
def lesson_notifications_view(request):
    if not has_school_role(
        request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN
    ):
        messages.error(request, "Lesson-plan updates are available only to teachers and school administrators.")
        return redirect("home")
    notifications = LessonNoteNotification.objects.filter(
        recipient=request.school_membership
    ).select_related("lesson_note")
    return render(request, "dashboard/lesson_notifications.html", {"notifications": notifications})


@login_required
def read_lesson_notification_view(request, notification_id):
    if not has_school_role(
        request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN
    ):
        messages.error(request, "Lesson-plan updates are available only to teachers and school administrators.")
        return redirect("home")
    if request.method == "POST":
        notification = get_object_or_404(
            LessonNoteNotification, pk=notification_id, recipient=request.school_membership
        )
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
    return redirect("lesson_notifications")

@login_required
def download_lesson_note_pdf(request, note_id):
    note = get_object_or_404(
        LessonNote, id=note_id, teacher=request.user, subject__school=request.school
    )

    import json
    try:
        lesson_data = json.loads(note.generated_content)
    except (json.JSONDecodeError, TypeError):
        lesson_data = None

    html_string = render_to_string("dashboard/lesson_note_pdf.html", {
        "note": note,
        "lesson_data": lesson_data,
    })

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{note.strand_topic}_lesson_note.pdf"'

    pisa_status = pisa.CreatePDF(html_string, dest=response)
    if pisa_status.err:
        return HttpResponse("Error generating PDF", status=500)

    return response


@login_required
def download_lesson_note_docx(request, note_id):
    note = get_object_or_404(
        LessonNote, id=note_id, teacher=request.user, subject__school=request.school
    )

    import json
    try:
        lesson_data = json.loads(note.generated_content)
    except (json.JSONDecodeError, TypeError):
        lesson_data = None

    buffer = build_lesson_note_docx(note, lesson_data)
    response = HttpResponse(
        buffer.read(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="{note.strand_topic}_lesson_note.docx"'
    return response


@login_required
def email_student_report_view(request, student_id, subject_id):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "This page is only available to teachers.")
        return redirect("home")

    if request.method != "POST":
        return redirect("student_report", student_id=student_id, subject_id=subject_id)

    student = get_object_or_404(User, id=student_id)
    subject = get_object_or_404(Subject, id=subject_id, school=request.school)

    if not Enrollment.objects.filter(student=student, subject=subject).exists():
        messages.error(request, "This student is not enrolled in this subject.")
        return redirect("teacher_dashboard")

    submissions = Submission.objects.filter(
        student=student, quiz__subject=subject
    ).select_related("quiz").prefetch_related("answers")

    report_text = generate_student_report(student, subject, submissions)

    success, result_message = send_report_email(student, subject, report_text)
    if success:
        messages.success(request, result_message)
    else:
        messages.error(request, result_message)

    return redirect("student_report", student_id=student.id, subject_id=subject.id)
