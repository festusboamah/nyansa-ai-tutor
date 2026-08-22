from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from academics.models import ClassEnrollment, SchoolClass, SubjectOffering, Term
from courses.models import Subject
from gradebook.models import Assessment
from quizzes.ai_quiz_generator import create_bank_questions
from quizzes.models import Quiz
from schools.models import SchoolMembership
from schools.services import has_school_role

from .forms import StrandForm, TopicForm
from .models import Misconception, RemediationPlan, StudyGoal, Strand, Topic
from .services import (
    add_topic_prerequisite, can_view_class, class_subject_mastery, goal_revision_status,
    misconception_patterns, remediation_plan_outcomes_for_classes, school_remediation_plan_outcomes,
    student_subject_mastery, topic_mastery_for_student, unmet_prerequisites, update_topic,
)

DIFFICULTY_BY_BAND = {
    "NEEDS_SUPPORT": "easy",
    "DEVELOPING": "medium",
    "MASTERED": "hard",
}


def mastery_staff_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not has_school_role(request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN):
            messages.error(request, "Mastery views are available only to school staff.")
            return redirect("home")
        return view(request, *args, **kwargs)
    return wrapped


def _selected_term(request):
    terms = Term.objects.filter(academic_year__school=request.school).select_related("academic_year")
    term_id = request.GET.get("term") or request.POST.get("term")
    return get_object_or_404(terms, pk=term_id) if term_id else terms.order_by("-academic_year__start_date", "-order").first()


@login_required
def mastery_overview_view(request):
    if not has_school_role(
        request, SchoolMembership.Role.STUDENT, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN,
    ):
        messages.error(request, "Mastery views are available only to students and school staff.")
        return redirect("home")

    term = _selected_term(request)
    terms = Term.objects.filter(academic_year__school=request.school).select_related("academic_year")
    if not term:
        return render(request, "mastery/overview.html", {"terms": terms})

    role = request.school_membership.role
    context = {"term": term, "terms": terms, "role": role}

    if role == SchoolMembership.Role.STUDENT:
        subjects = Subject.objects.filter(
            school=request.school, enrollments__student=request.user
        ).distinct()
        context["subject_rows"] = [
            student_subject_mastery(request.school_membership, subject, term) for subject in subjects
        ]
    elif role == SchoolMembership.Role.SCHOOL_ADMIN:
        context["classes"] = SchoolClass.objects.filter(school=request.school, academic_year=term.academic_year)
    else:
        context["classes"] = SchoolClass.objects.filter(
            Q(class_teacher=request.school_membership)
            | Q(subject_offerings__term=term, subject_offerings__teacher_assignments__teacher=request.school_membership),
            school=request.school, academic_year=term.academic_year,
        ).distinct()

    return render(request, "mastery/overview.html", context)


@login_required
def study_goals_view(request):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "Study goals are available only to students.")
        return redirect("home")

    term = _selected_term(request)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create":
            topic = get_object_or_404(
                Topic, pk=request.POST.get("topic_id"),
                strand__subject__school=request.school,
                strand__subject__enrollments__student=request.user,
            )
            if StudyGoal.objects.filter(
                student=request.school_membership, topic=topic, status=StudyGoal.Status.ACTIVE,
            ).exists():
                messages.error(request, "You already have an active goal for this topic.")
            else:
                StudyGoal.objects.create(
                    school=request.school, student=request.school_membership, topic=topic,
                    note=request.POST.get("note", "").strip(),
                )
                messages.success(request, "Study goal created.")
            return redirect("mastery_study_goals")

        if action in ("achieve", "abandon"):
            goal = get_object_or_404(
                StudyGoal, pk=request.POST.get("goal_id"), student=request.school_membership,
                status=StudyGoal.Status.ACTIVE,
            )
            if action == "achieve":
                goal.status = StudyGoal.Status.ACHIEVED
                goal.achieved_at = timezone.now()
                goal.save(update_fields=["status", "achieved_at"])
                messages.success(request, "Goal marked achieved. Nice work!")
            else:
                goal.status = StudyGoal.Status.ABANDONED
                goal.save(update_fields=["status"])
                messages.success(request, "Goal abandoned.")
            return redirect("mastery_study_goals")

    goals = StudyGoal.objects.filter(
        student=request.school_membership, status=StudyGoal.Status.ACTIVE,
    ).select_related("topic__strand__subject")
    goal_rows = [{"goal": goal, "status": goal_revision_status(goal, term)} for goal in goals]

    topics = Topic.objects.filter(
        strand__subject__school=request.school, strand__subject__enrollments__student=request.user,
    ).select_related("strand__subject")

    return render(request, "mastery/study_goals.html", {
        "goal_rows": goal_rows, "topics": topics,
    })


@login_required
def improvement_report_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN):
        messages.error(request, "The improvement report is available only to school staff.")
        return redirect("home")

    term = _selected_term(request)
    terms = Term.objects.filter(academic_year__school=request.school).select_related("academic_year")
    if not term:
        return render(request, "mastery/improvement_report.html", {"terms": terms})

    role = request.school_membership.role
    context = {"term": term, "terms": terms}

    if role == SchoolMembership.Role.SCHOOL_ADMIN:
        context["outcomes"] = school_remediation_plan_outcomes(request.school, term)
    else:
        classes = SchoolClass.objects.filter(
            Q(class_teacher=request.school_membership)
            | Q(subject_offerings__term=term, subject_offerings__teacher_assignments__teacher=request.school_membership),
            school=request.school, academic_year=term.academic_year,
        ).distinct()
        context["outcomes"] = remediation_plan_outcomes_for_classes(classes, term)

    return render(request, "mastery/improvement_report.html", context)


@mastery_staff_required
def class_detail_view(request, class_id, term_id):
    school_class = get_object_or_404(SchoolClass, pk=class_id, school=request.school)
    term = get_object_or_404(Term, pk=term_id, academic_year=school_class.academic_year)
    if not can_view_class(request.school_membership, school_class, term):
        raise PermissionDenied

    subjects = Subject.objects.filter(
        school=request.school, offerings__school_class=school_class, offerings__term=term
    ).distinct()
    subject_rows = [class_subject_mastery(school_class, subject, term) for subject in subjects]
    return render(request, "mastery/class_detail.html", {
        "school_class": school_class, "term": term, "subject_rows": subject_rows,
    })


@mastery_staff_required
def differentiated_tasks_view(request, class_id, term_id, topic_id):
    school_class = get_object_or_404(SchoolClass, pk=class_id, school=request.school)
    term = get_object_or_404(Term, pk=term_id, academic_year=school_class.academic_year)
    if not can_view_class(request.school_membership, school_class, term):
        raise PermissionDenied
    topic = get_object_or_404(Topic, pk=topic_id, strand__subject__school=request.school)

    roster = ClassEnrollment.objects.filter(
        school_class=school_class, status=ClassEnrollment.Status.ACTIVE
    ).select_related("student__user")

    bands = {"MASTERED": [], "DEVELOPING": [], "NEEDS_SUPPORT": [], "NO_EVIDENCE": []}
    for enrollment in roster:
        result = topic_mastery_for_student(enrollment.student, topic, term)
        entry = {"student": enrollment.student, "result": result}
        if result["status"] == "NEEDS_SUPPORT":
            entry["active_plan"] = RemediationPlan.objects.filter(
                student=enrollment.student, topic=topic, term=term, status=RemediationPlan.Status.ACTIVE,
            ).first()
            entry["unmet_prerequisites"] = unmet_prerequisites(enrollment.student, topic, term)
        bands[result["status"]].append(entry)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create_plan":
            enrollment = get_object_or_404(
                ClassEnrollment, school_class=school_class, student_id=request.POST.get("student_id"),
                status=ClassEnrollment.Status.ACTIVE,
            )
            plan_text = request.POST.get("plan_text", "").strip()
            if plan_text:
                mastery_now = topic_mastery_for_student(enrollment.student, topic, term)
                RemediationPlan.objects.create(
                    school=request.school, student=enrollment.student, topic=topic, term=term,
                    plan=plan_text, mastery_percentage_at_start=mastery_now["mastery_percentage"],
                    created_by=request.school_membership,
                )
                messages.success(request, "Remediation plan created.")
            return redirect("mastery_differentiate", class_id=school_class.pk, term_id=term.pk, topic_id=topic.pk)

        if action in ("complete_plan", "cancel_plan"):
            plan = get_object_or_404(
                RemediationPlan, pk=request.POST.get("plan_id"), topic=topic, term=term,
                status=RemediationPlan.Status.ACTIVE,
            )
            if action == "complete_plan":
                outcome = request.POST.get("outcome", "").strip()
                if outcome:
                    mastery_now = topic_mastery_for_student(plan.student, topic, term)
                    plan.status = RemediationPlan.Status.COMPLETED
                    plan.outcome = outcome
                    plan.mastery_percentage_at_completion = mastery_now["mastery_percentage"]
                    plan.completed_at = timezone.now()
                    plan.save(update_fields=[
                        "status", "outcome", "mastery_percentage_at_completion", "completed_at",
                    ])
                    messages.success(request, "Remediation plan marked complete.")
            else:
                plan.status = RemediationPlan.Status.CANCELLED
                plan.save(update_fields=["status"])
                messages.success(request, "Remediation plan cancelled.")
            return redirect("mastery_differentiate", class_id=school_class.pk, term_id=term.pk, topic_id=topic.pk)

        difficulty = DIFFICULTY_BY_BAND.get(action)
        if difficulty and bands.get(action):
            topic_description = request.POST.get("topic_description") or topic.name
            try:
                num_questions = int(request.POST.get("num_questions", 3))
            except ValueError:
                num_questions = 3
            num_questions = max(1, min(num_questions, 15))

            created = create_bank_questions(
                subject=topic.strand.subject, topic=topic, difficulty=difficulty,
                topic_description=topic_description, num_questions=num_questions,
                created_by=request.user,
            )
            if created:
                messages.success(
                    request,
                    f"Generated {len(created)} {difficulty} question(s) for review in the question bank.",
                )
            else:
                messages.error(request, "AI generation failed. Please try again.")
        return redirect("mastery_differentiate", class_id=school_class.pk, term_id=term.pk, topic_id=topic.pk)

    return render(request, "mastery/differentiated_tasks.html", {
        "school_class": school_class, "term": term, "topic": topic, "bands": bands,
    })


@login_required
def curriculum_view(request):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied

    if request.method == "POST" and request.POST.get("action") in ("add_prerequisite", "remove_prerequisite"):
        topic = get_object_or_404(
            Topic, pk=request.POST.get("topic_id"), strand__subject__school=request.school
        )
        prerequisite = get_object_or_404(
            Topic, pk=request.POST.get("prerequisite_id"), strand__subject__school=request.school
        )
        if request.POST.get("action") == "add_prerequisite":
            try:
                add_topic_prerequisite(topic, prerequisite)
                messages.success(request, "Prerequisite added.")
            except ValidationError as error:
                messages.error(request, "; ".join(error.messages))
        else:
            topic.prerequisites.remove(prerequisite)
            messages.success(request, "Prerequisite removed.")
        return redirect("mastery_curriculum")

    if request.method == "POST" and request.POST.get("action") == "edit_topic":
        topic = get_object_or_404(
            Topic, pk=request.POST.get("topic_id"), strand__subject__school=request.school
        )
        strand_id = request.POST.get("strand_id")
        strand = get_object_or_404(Strand, pk=strand_id, school=request.school) if strand_id else None
        try:
            update_topic(
                topic=topic, actor=request.school_membership,
                name=request.POST.get("name", "").strip() or None, strand=strand,
                reason=request.POST.get("reason", ""),
            )
            messages.success(request, "Topic updated.")
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        return redirect("mastery_curriculum")

    strand_form = StrandForm(
        request.POST if request.POST.get("form") == "strand" else None, school=request.school
    )
    topic_form = TopicForm(
        request.POST if request.POST.get("form") == "topic" else None, school=request.school
    )
    if request.method == "POST" and request.POST.get("form") == "strand" and strand_form.is_valid():
        strand = strand_form.save(commit=False)
        strand.school = request.school
        strand.full_clean()
        strand.save()
        messages.success(request, "Strand saved.")
        return redirect("mastery_curriculum")
    if request.method == "POST" and request.POST.get("form") == "topic" and topic_form.is_valid():
        topic = topic_form.save(commit=False)
        topic.full_clean()
        topic.save()
        messages.success(request, "Topic saved.")
        return redirect("mastery_curriculum")

    return render(request, "mastery/curriculum.html", {
        "strand_form": strand_form, "topic_form": topic_form,
        "strands": Strand.objects.filter(school=request.school).prefetch_related(
            "topics__prerequisites", "topics__revisions__changed_by__user"
        ),
        "all_topics": Topic.objects.filter(strand__subject__school=request.school).select_related("strand"),
    })


@login_required
def assign_topics_view(request, offering_id):
    offering = get_object_or_404(
        SubjectOffering.objects.select_related("school_class", "term", "subject"),
        pk=offering_id, school=request.school,
    )
    if not has_school_role(request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied
    if request.school_membership.role == SchoolMembership.Role.TEACHER and not (
        offering.teacher_assignments.filter(teacher=request.school_membership).exists()
        or offering.school_class.class_teacher_id == request.school_membership.id
    ):
        raise PermissionDenied

    topics = Topic.objects.filter(strand__subject=offering.subject).select_related("strand")
    if request.method == "POST":
        valid_topic_ids = set(topics.values_list("id", flat=True))
        for assessment in Assessment.objects.filter(offering=offering):
            field_name = f"topic_{assessment.pk}"
            if field_name not in request.POST:
                continue
            topic_id = request.POST[field_name]
            try:
                topic_id = int(topic_id) if topic_id else None
            except ValueError:
                topic_id = None
            if topic_id is not None and topic_id not in valid_topic_ids:
                topic_id = None
            assessment.topic_id = topic_id
            assessment.save(update_fields=["topic"])
        messages.success(request, "Topic assignments saved.")
        return redirect("mastery_assign_topics", offering_id=offering.pk)

    return render(request, "mastery/assign_topics.html", {
        "offering": offering, "topics": topics,
        "assessments": Assessment.objects.filter(offering=offering).select_related("topic"),
    })


@login_required
def assign_question_topics_view(request, quiz_id):
    quiz = get_object_or_404(Quiz.objects.select_related("subject"), pk=quiz_id, subject__school=request.school)
    if not has_school_role(request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied
    if request.school_membership.role == SchoolMembership.Role.TEACHER and quiz.teacher_id != request.user.id:
        raise PermissionDenied

    topics = Topic.objects.filter(strand__subject=quiz.subject).select_related("strand")
    if request.method == "POST":
        valid_topic_ids = set(topics.values_list("id", flat=True))
        for question in quiz.questions.all():
            field_name = f"topic_{question.pk}"
            if field_name not in request.POST:
                continue
            topic_id = request.POST[field_name]
            try:
                topic_id = int(topic_id) if topic_id else None
            except ValueError:
                topic_id = None
            if topic_id is not None and topic_id not in valid_topic_ids:
                topic_id = None
            question.topic_id = topic_id
            question.save(update_fields=["topic"])
        messages.success(request, "Question topic assignments saved.")
        return redirect("mastery_assign_question_topics", quiz_id=quiz.pk)

    return render(request, "mastery/assign_question_topics.html", {
        "quiz": quiz, "topics": topics,
        "questions": quiz.questions.all().select_related("topic"),
    })


@mastery_staff_required
def misconceptions_view(request, class_id, term_id):
    school_class = get_object_or_404(SchoolClass, pk=class_id, school=request.school)
    term = get_object_or_404(Term, pk=term_id, academic_year=school_class.academic_year)
    if not can_view_class(request.school_membership, school_class, term):
        raise PermissionDenied

    roster_student_ids = ClassEnrollment.objects.filter(
        school_class=school_class, status=ClassEnrollment.Status.ACTIVE
    ).values_list("student_id", flat=True)

    if request.method == "POST":
        misconception = get_object_or_404(
            Misconception, pk=request.POST.get("misconception_id"), student_id__in=roster_student_ids,
        )
        action = request.POST.get("action")
        if action in ("dismiss", "resolve"):
            misconception.status = (
                Misconception.Status.DISMISSED if action == "dismiss" else Misconception.Status.RESOLVED
            )
            misconception.reviewed_by = request.school_membership
            misconception.reviewed_at = timezone.now()
            misconception.save(update_fields=["status", "reviewed_by", "reviewed_at"])
            messages.success(request, "Misconception updated.")
        return redirect("mastery_misconceptions", class_id=school_class.pk, term_id=term.pk)

    misconceptions = Misconception.objects.filter(
        student_id__in=roster_student_ids, status=Misconception.Status.OPEN
    ).select_related("student__user", "topic__strand")

    return render(request, "mastery/misconceptions.html", {
        "school_class": school_class, "term": term, "misconceptions": misconceptions,
        "patterns": misconception_patterns(school_class, term),
    })
