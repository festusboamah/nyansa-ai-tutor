from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Subject, Enrollment, Material, StudyDocument, StudyQuestion
from .forms import SubjectForm, MaterialForm
from .study_ai import (
    extract_text_from_pdf,
    generate_summary,
    answer_question_about_document,
    get_or_extract_material_text,
)
from quizzes.models import Quiz, Submission
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa
from schools.models import SchoolMembership
from schools.services import has_school_role


@login_required
def dashboard_view(request):
    if has_school_role(request, SchoolMembership.Role.TEACHER):
        return redirect("teacher_dashboard")

    from .grading import calculate_subject_grade
    from quizzes.models import Quiz, Assignment
    from django.utils import timezone

    enrollments = Enrollment.objects.filter(
        student=request.user, subject__school=request.school
    ).select_related("subject")
    subjects_with_grades = []
    for e in enrollments:
        grade_data = calculate_subject_grade(request.user, e.subject)
        subjects_with_grades.append({"subject": e.subject, "grade_data": grade_data})

    enrolled_subject_ids = [e.subject.id for e in enrollments]
    now = timezone.now()

    upcoming_quizzes = Quiz.objects.filter(
        subject_id__in=enrolled_subject_ids, deadline__gte=now
    ).order_by("deadline")[:5]

    upcoming_assignments = Assignment.objects.filter(
        subject_id__in=enrolled_subject_ids, deadline__gte=now
    ).order_by("deadline")[:5]

    upcoming_items = []
    for q in upcoming_quizzes:
        upcoming_items.append({"title": q.title, "subject": q.subject.name, "deadline": q.deadline, "type": "Quiz" if q.assessment_type == "QUIZ" else "Exam", "url_name": "quiz_start", "url_id": q.id})
    for a in upcoming_assignments:
        upcoming_items.append({"title": a.title, "subject": a.subject.name, "deadline": a.deadline, "type": "Assignment", "url_name": "assignment_detail", "url_id": a.id})

    upcoming_items.sort(key=lambda x: x["deadline"])

    from mastery.models import StudyGoal
    from mastery.services import goal_revision_status

    active_goals = StudyGoal.objects.filter(
        student=request.school_membership, status=StudyGoal.Status.ACTIVE,
    )
    due_goal_count = sum(1 for goal in active_goals if goal_revision_status(goal, term=None)["due"])

    return render(request, "courses/student_dashboard.html", {
        "subjects_with_grades": subjects_with_grades,
        "upcoming_items": upcoming_items[:5],
        "due_goal_count": due_goal_count,
    })


@login_required
def browse_subjects_view(request):
    all_subjects = Subject.objects.filter(school=request.school)
    enrolled_ids = Enrollment.objects.filter(
        student=request.user, subject__school=request.school
    ).values_list("subject_id", flat=True)
    return render(request, "courses/browse_subjects.html", {
        "subjects": all_subjects,
        "enrolled_ids": list(enrolled_ids),
    })


@login_required
def enroll_view(request, subject_id):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "Only students can enroll in subjects.")
        return redirect("home")

    subject = get_object_or_404(Subject, id=subject_id, school=request.school)
    Enrollment.objects.get_or_create(student=request.user, subject=subject)
    messages.success(request, f"You are now enrolled in {subject.name}!")
    return redirect("browse_subjects")


@login_required
def subject_detail_view(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id, school=request.school)
    is_enrolled = Enrollment.objects.filter(student=request.user, subject=subject).exists()

    if not is_enrolled and not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "You need to enroll in this subject first.")
        return redirect("browse_subjects")

    materials = subject.materials.all()
    quizzes = subject.quizzes.all()
    if not has_school_role(request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN):
        quizzes = quizzes.exclude(status=Quiz.Status.DRAFT)
    assignments = subject.assignments.all()
    return render(request, "courses/subject_detail.html", {
        "subject": subject,
        "materials": materials,
        "quizzes": quizzes,
        "assignments": assignments,
    })


@login_required
def material_text_view(request, material_id):
    material = get_object_or_404(Material, id=material_id, subject__school=request.school)
    is_enrolled = Enrollment.objects.filter(student=request.user, subject=material.subject).exists()

    if not is_enrolled and not has_school_role(
        request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN
    ):
        messages.error(request, "You need to enroll in this subject first.")
        return redirect("browse_subjects")

    text = get_or_extract_material_text(material)
    return render(request, "courses/material_text.html", {
        "material": material,
        "text": text,
    })


@login_required
def create_subject_view(request):
    if not has_school_role(
        request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN
    ):
        messages.error(request, "Only teachers can create subjects.")
        return redirect("home")

    if request.school is None:
        messages.error(request, "Select an active school before creating a subject.")
        return redirect("home")

    if request.method == "POST":
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save(commit=False)
            subject.school = request.school
            subject.save()
            messages.success(request, "Subject created successfully!")
            return redirect("teacher_dashboard")
    else:
        form = SubjectForm()

    return render(request, "courses/create_subject.html", {"form": form})


@login_required
def create_material_view(request):
    if not has_school_role(
        request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN
    ):
        messages.error(request, "Only teachers can add materials.")
        return redirect("home")

    if request.school is None:
        messages.error(request, "Select an active school before adding materials.")
        return redirect("home")

    if request.method == "POST":
        form = MaterialForm(request.POST, request.FILES, school=request.school)
        if form.is_valid():
            material = form.save(commit=False)
            material.teacher = request.user
            material.save()
            messages.success(request, "Material added successfully!")
            return redirect("teacher_dashboard")
    else:
        form = MaterialForm(school=request.school)

    return render(request, "courses/create_material.html", {"form": form})


@login_required
def study_documents_view(request):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "This feature is only available to students.")
        return redirect("home")

    documents = StudyDocument.objects.filter(
        student=request.user, school=request.school
    ).order_by("-uploaded_at")
    return render(request, "courses/study_documents.html", {"documents": documents})


@login_required
def upload_study_document_view(request):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "This feature is only available to students.")
        return redirect("home")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        uploaded_file = request.FILES.get("file")

        if not title or not uploaded_file:
            messages.error(request, "Please provide a title and select a PDF file.")
            return redirect("upload_study_document")

        document = StudyDocument.objects.create(
            student=request.user,
            school=request.school,
            title=title,
            file=uploaded_file,
        )

        document.file.seek(0)
        extracted = extract_text_from_pdf(document.file)
        document.extracted_text = extracted
        document.summary = generate_summary(extracted)
        document.save()

        messages.success(request, "Document uploaded and summarized!")
        return redirect("study_document_detail", document_id=document.id)

    return render(request, "courses/upload_study_document.html")


@login_required
def study_document_detail_view(request, document_id):
    document = get_object_or_404(
        StudyDocument, id=document_id, student=request.user, school=request.school
    )
    previous_questions = document.questions.all().order_by("asked_at")

    if request.method == "POST":
        question_text = request.POST.get("question", "").strip()
        if question_text:
            previous_qa = [(q.question, q.answer) for q in previous_questions]
            answer = answer_question_about_document(
                document.extracted_text, question_text, previous_qa
            )
            StudyQuestion.objects.create(
                document=document, question=question_text, answer=answer
            )
        return redirect("study_document_detail", document_id=document.id)

    return render(request, "courses/study_document_detail.html", {
        "document": document,
        "previous_questions": previous_questions,
    })


@login_required
def unenroll_view(request, subject_id):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "Only students can unenroll from subjects.")
        return redirect("home")

    subject = get_object_or_404(Subject, id=subject_id, school=request.school)
    enrollment = Enrollment.objects.filter(student=request.user, subject=subject).first()

    if enrollment:
        enrollment.delete()
        messages.success(request, f"You have unenrolled from {subject.name}.")
    else:
        messages.error(request, "You are not enrolled in this subject.")

    return redirect("dashboard")


@login_required
def transcript_view(request):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "This feature is only available to students.")
        return redirect("home")

    submissions = Submission.objects.filter(
        student=request.user, quiz__subject__school=request.school
    ).select_related("quiz", "quiz__subject").order_by("quiz__subject__name", "-submitted_at")

    subjects_data = {}
    for sub in submissions:
        subject_name = sub.quiz.subject.name
        if subject_name not in subjects_data:
            subjects_data[subject_name] = []
        subjects_data[subject_name].append(sub)

    all_scores = [s.score for s in submissions if s.score is not None]
    overall_average = round(sum(all_scores) / len(all_scores), 1) if all_scores else None

    transcript_sections = []
    for subject_name, subs in subjects_data.items():
        scores = [s.score for s in subs if s.score is not None]
        avg = round(sum(scores) / len(scores), 1) if scores else None
        transcript_sections.append({
            "subject_name": subject_name,
            "submissions": subs,
            "average": avg,
        })

    return render(request, "courses/transcript.html", {
        "transcript_sections": transcript_sections,
        "overall_average": overall_average,
        "total_quizzes": submissions.count(),
    })


@login_required
def download_transcript_pdf(request):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "This feature is only available to students.")
        return redirect("home")

    submissions = Submission.objects.filter(
        student=request.user, quiz__subject__school=request.school
    ).select_related("quiz", "quiz__subject").order_by("quiz__subject__name", "-submitted_at")

    subjects_data = {}
    for sub in submissions:
        subject_name = sub.quiz.subject.name
        if subject_name not in subjects_data:
            subjects_data[subject_name] = []
        subjects_data[subject_name].append(sub)

    all_scores = [s.score for s in submissions if s.score is not None]
    overall_average = round(sum(all_scores) / len(all_scores), 1) if all_scores else None

    transcript_sections = []
    for subject_name, subs in subjects_data.items():
        scores = [s.score for s in subs if s.score is not None]
        avg = round(sum(scores) / len(scores), 1) if scores else None
        transcript_sections.append({
            "subject_name": subject_name,
            "submissions": subs,
            "average": avg,
        })

    html_string = render_to_string("courses/transcript_pdf.html", {
        "transcript_sections": transcript_sections,
        "overall_average": overall_average,
        "total_quizzes": submissions.count(),
        "student": request.user,
    })

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{request.user.username}_transcript.pdf"'

    pisa_status = pisa.CreatePDF(html_string, dest=response)
    if pisa_status.err:
        return HttpResponse("Error generating PDF", status=500)

    return response
