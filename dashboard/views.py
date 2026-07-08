from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from courses.models import Subject, Enrollment
from quizzes.models import Quiz, Submission
from accounts.models import User
from .ai_reports import generate_student_report


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

    return render(request, "dashboard/teacher_dashboard.html", {
        "subject_data": subject_data,
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