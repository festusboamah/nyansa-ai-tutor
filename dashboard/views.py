from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from courses.models import Subject, Enrollment
from quizzes.models import Quiz, Submission
from accounts.models import User
from .ai_reports import generate_student_report
from .models import LessonNote
from .forms import LessonNoteForm
from .lesson_ai import generate_lesson_note
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa
import markdown as md


@login_required
def teacher_dashboard_view(request):
    if not request.user.is_teacher():
        messages.error(request, "This page is only available to teachers.")
        return redirect("home")

    subjects = Subject.objects.filter(materials__teacher=request.user).distinct()
    if not subjects.exists():
        subjects = Subject.objects.filter(quizzes__teacher=request.user).distinct()

    subject_data = []
    for subject in subjects:
        enrollments = Enrollment.objects.filter(subject=subject).select_related("student")
        subject_data.append({
            "subject": subject,
            "student_count": enrollments.count(),
            "enrollments": enrollments,
        })

    from quizzes.models import Assignment
    assignments = Assignment.objects.filter(teacher=request.user).select_related("subject").order_by("-created_at")

    return render(request, "dashboard/teacher_dashboard.html", {
        "subject_data": subject_data,
        "assignments": assignments,
    })


@login_required
def student_report_view(request, student_id, subject_id):
    if not request.user.is_teacher():
        messages.error(request, "This page is only available to teachers.")
        return redirect("home")

    student = get_object_or_404(User, id=student_id)
    subject = get_object_or_404(Subject, id=subject_id)

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
def lesson_notes_list_view(request):
    if not request.user.is_teacher():
        messages.error(request, "This feature is only available to teachers.")
        return redirect("home")

    notes = LessonNote.objects.filter(teacher=request.user).order_by("-created_at")
    return render(request, "dashboard/lesson_notes_list.html", {"notes": notes})


@login_required
def create_lesson_note_view(request):
    if not request.user.is_teacher():
        messages.error(request, "This feature is only available to teachers.")
        return redirect("home")

    if request.method == "POST":
        form = LessonNoteForm(request.POST)
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
            )

            if result is None:
                messages.error(request, "AI generation failed. Please try again.")
                lesson_note.delete()
                return redirect("create_lesson_note")

            import json
            lesson_note.generated_content = json.dumps(result)
            if not lesson_note.content_standard:
                lesson_note.content_standard = result.get("content_standard", "")
            if not lesson_note.performance_indicator:
                lesson_note.performance_indicator = result.get("performance_indicators", "")
            if not lesson_note.resources:
                lesson_note.resources = result.get("resources", "")
            lesson_note.save()

            messages.success(request, "Lesson note generated successfully!")
            return redirect("lesson_note_detail", note_id=lesson_note.id)
    else:
        form = LessonNoteForm()

    return render(request, "dashboard/create_lesson_note.html", {"form": form})


@login_required
def lesson_note_detail_view(request, note_id):
    note = get_object_or_404(LessonNote, id=note_id, teacher=request.user)
    import json
    try:
        lesson_data = json.loads(note.generated_content)
    except (json.JSONDecodeError, TypeError):
        lesson_data = None
    return render(request, "dashboard/lesson_note_detail.html", {"note": note, "lesson_data": lesson_data})

@login_required
def download_lesson_note_pdf(request, note_id):
    note = get_object_or_404(LessonNote, id=note_id, teacher=request.user)

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