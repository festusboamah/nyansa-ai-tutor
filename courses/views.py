from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Subject, Enrollment, Material, StudyDocument, StudyQuestion
from .forms import SubjectForm, MaterialForm
from .study_ai import extract_text_from_pdf, generate_summary, answer_question_about_document

@login_required
def dashboard_view(request):
    if request.user.is_teacher():
        return redirect("teacher_dashboard")

    enrollments = Enrollment.objects.filter(student=request.user).select_related("subject")
    subjects = [e.subject for e in enrollments]
    return render(request, "courses/student_dashboard.html", {"subjects": subjects})


@login_required
def browse_subjects_view(request):
    all_subjects = Subject.objects.all()
    enrolled_ids = Enrollment.objects.filter(student=request.user).values_list("subject_id", flat=True)
    return render(request, "courses/browse_subjects.html", {
        "subjects": all_subjects,
        "enrolled_ids": list(enrolled_ids),
    })


@login_required
def enroll_view(request, subject_id):
    if not request.user.is_student():
        messages.error(request, "Only students can enroll in subjects.")
        return redirect("home")

    subject = get_object_or_404(Subject, id=subject_id)
    Enrollment.objects.get_or_create(student=request.user, subject=subject)
    messages.success(request, f"You are now enrolled in {subject.name}!")
    return redirect("browse_subjects")


@login_required
def subject_detail_view(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    is_enrolled = Enrollment.objects.filter(student=request.user, subject=subject).exists()

    if not is_enrolled and not request.user.is_teacher():
        messages.error(request, "You need to enroll in this subject first.")
        return redirect("browse_subjects")

    materials = subject.materials.all()
    quizzes = subject.quizzes.all()
    return render(request, "courses/subject_detail.html", {
        "subject": subject,
        "materials": materials,
        "quizzes": quizzes,
    })

@login_required
def create_subject_view(request):
    if not request.user.is_teacher():
        messages.error(request, "Only teachers can create subjects.")
        return redirect("home")

    if request.method == "POST":
        form = SubjectForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Subject created successfully!")
            return redirect("teacher_dashboard")
    else:
        form = SubjectForm()

    return render(request, "courses/create_subject.html", {"form": form})


@login_required
def create_material_view(request):
    if not request.user.is_teacher():
        messages.error(request, "Only teachers can add materials.")
        return redirect("home")

    if request.method == "POST":
        form = MaterialForm(request.POST, request.FILES)
        if form.is_valid():
            material = form.save(commit=False)
            material.teacher = request.user
            material.save()
            messages.success(request, "Material added successfully!")
            return redirect("teacher_dashboard")
    else:
        form = MaterialForm()

    return render(request, "courses/create_material.html", {"form": form})

@login_required
def study_documents_view(request):
    if not request.user.is_student():
        messages.error(request, "This feature is only available to students.")
        return redirect("home")

    documents = StudyDocument.objects.filter(student=request.user).order_by("-uploaded_at")
    return render(request, "courses/study_documents.html", {"documents": documents})


@login_required
def upload_study_document_view(request):
    if not request.user.is_student():
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
    document = get_object_or_404(StudyDocument, id=document_id, student=request.user)
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
    if not request.user.is_student():
        messages.error(request, "Only students can unenroll from subjects.")
        return redirect("home")

    subject = get_object_or_404(Subject, id=subject_id)
    enrollment = Enrollment.objects.filter(student=request.user, subject=subject).first()

    if enrollment:
        enrollment.delete()
        messages.success(request, f"You have unenrolled from {subject.name}.")
    else:
        messages.error(request, "You are not enrolled in this subject.")

    return redirect("dashboard")