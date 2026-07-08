from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Subject, Enrollment, Material
from .forms import SubjectForm, MaterialForm


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