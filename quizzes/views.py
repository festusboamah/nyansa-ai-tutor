from decimal import Decimal
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseBadRequest, HttpResponseNotAllowed, JsonResponse
from django.utils import timezone
from .models import Quiz, QuizGenerationSettings, Question, Choice, Submission, Answer, Badge
from .models import BankQuestion, BankQuestionChoice, ExamFeeWaiver, ExamIntegrityEvent, ExamSnapshot
from .ai_grading import grade_short_answer, generate_submission_feedback
from .forms import QuizForm, QuestionForm, ChoiceFormSet, AIQuizGenerationForm, BankQuestionGenerationForm
from .ai_quiz_generator import generate_quiz_questions, create_bank_questions
from .models import Assignment, AssignmentSubmission, CriterionScore
from .assignment_forms import AssignmentForm, AssignmentSubmissionForm, GradeAssignmentForm, RubricCriterionFormSet
from .assignment_ai import extract_text_from_file, suggest_assignment_grade
from .exam_ai import suggest_essay_grade
from .exam_attempts import exam_start_blocker, create_exam_submission
from .exam_fees import fee_balance_blocks_exam, get_fee_balance
from .exam_forms import ExamOfferingsForm, EssayGradingFormSet
from .exam_roster import eligible_students_for_exam, student_may_sit_exam
from .exam_scoring import finalize_exam_attempt, recompute_exam_score
from schools.models import SchoolMembership
from schools.services import has_school_role


@login_required
def quiz_start_view(request, quiz_id):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "Only students can take quizzes.")
        return redirect("home")

    quiz = get_object_or_404(Quiz, id=quiz_id, subject__school=request.school)
    if quiz.status == Quiz.Status.DRAFT:
        messages.error(request, "This quiz hasn't been published by your teacher yet.")
        return redirect("dashboard")

    question_count = quiz.questions.count()
    attempts_used = Submission.objects.filter(quiz=quiz, student=request.user).count()
    attempts_remaining = quiz.max_attempts - attempts_used

    if quiz.assessment_type == Quiz.AssessmentType.EXAM:
        on_roster = student_may_sit_exam(quiz, request.school_membership)
        fee_blocked = on_roster and fee_balance_blocks_exam(request.school_membership, quiz)
        in_progress_submission = Submission.objects.filter(
            quiz=quiz, student=request.user, submitted_at__isnull=True
        ).first()
        return render(request, "quizzes/exam_start.html", {
            "quiz": quiz,
            "question_count": question_count,
            "attempts_used": attempts_used,
            "attempts_remaining": attempts_remaining,
            "past_deadline": quiz.is_past_deadline(),
            "before_start": quiz.is_before_start(),
            "on_roster": on_roster,
            "fee_blocked": fee_blocked,
            "in_progress_submission": in_progress_submission,
        })

    if quiz.offerings.exists() and not student_may_sit_exam(quiz, request.school_membership):
        messages.error(request, "This quiz is restricted to a class you are not part of.")
        return redirect("dashboard")

    return render(request, "quizzes/quiz_start.html", {
        "quiz": quiz,
        "question_count": question_count,
        "attempts_used": attempts_used,
        "attempts_remaining": attempts_remaining,
        "past_deadline": quiz.is_past_deadline(),
    })


@login_required
def start_exam_attempt_view(request, quiz_id):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "Only students can take exams.")
        return redirect("home")
    if request.method != "POST":
        return redirect("quiz_start", quiz_id=quiz_id)

    quiz = get_object_or_404(
        Quiz, id=quiz_id, subject__school=request.school, assessment_type=Quiz.AssessmentType.EXAM
    )
    if quiz.status == Quiz.Status.DRAFT:
        messages.error(request, "This exam hasn't been published yet.")
        return redirect("dashboard")

    existing = Submission.objects.filter(
        quiz=quiz, student=request.user, submitted_at__isnull=True
    ).first()
    if existing:
        return redirect("exam_take", quiz_id=quiz.id, submission_id=existing.id)

    if quiz.require_webcam_snapshots:
        return redirect("exam_consent", quiz_id=quiz.id)

    error = exam_start_blocker(quiz, request.user, request.school_membership)
    if error:
        messages.error(request, error)
        return redirect("quiz_start", quiz_id=quiz.id)

    submission = create_exam_submission(quiz, request.user)
    return redirect("exam_take", quiz_id=quiz.id, submission_id=submission.id)


@login_required
def exam_consent_view(request, quiz_id):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "Only students can take exams.")
        return redirect("home")

    quiz = get_object_or_404(
        Quiz, id=quiz_id, subject__school=request.school,
        assessment_type=Quiz.AssessmentType.EXAM, require_webcam_snapshots=True,
    )
    if quiz.status == Quiz.Status.DRAFT:
        messages.error(request, "This exam hasn't been published yet.")
        return redirect("dashboard")

    existing = Submission.objects.filter(
        quiz=quiz, student=request.user, submitted_at__isnull=True
    ).first()
    if existing:
        return redirect("exam_take", quiz_id=quiz.id, submission_id=existing.id)

    error = exam_start_blocker(quiz, request.user, request.school_membership)
    if error:
        messages.error(request, error)
        return redirect("quiz_start", quiz_id=quiz.id)

    if request.method == "POST":
        if request.POST.get("consent") != "yes":
            messages.error(request, "You must agree to the exam monitoring policy to begin.")
            return redirect("quiz_start", quiz_id=quiz.id)
        submission = create_exam_submission(quiz, request.user, camera_consent_given=True)
        return redirect("exam_take", quiz_id=quiz.id, submission_id=submission.id)

    return render(request, "quizzes/exam_consent.html", {"quiz": quiz})


@login_required
def exam_take_view(request, quiz_id, submission_id):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "Only students can take exams.")
        return redirect("home")

    quiz = get_object_or_404(
        Quiz, id=quiz_id, subject__school=request.school, assessment_type=Quiz.AssessmentType.EXAM
    )
    submission = get_object_or_404(Submission, id=submission_id, quiz=quiz, student=request.user)

    if submission.is_finished():
        return redirect("quiz_result", submission_id=submission.id)

    grace = timedelta(seconds=30)
    past_cutoff = submission.expires_at is not None and timezone.now() > submission.expires_at + grace

    if request.method == "POST":
        if past_cutoff:
            finalize_exam_attempt(quiz, submission, {}, {})
            messages.error(
                request,
                "Time expired before your submission was received. Your exam was submitted with "
                "whatever answers had already been saved.",
            )
        else:
            finalize_exam_attempt(quiz, submission, request.POST, request.FILES)
            messages.success(request, "Exam submitted successfully!")
        return redirect("quiz_result", submission_id=submission.id)

    if submission.is_expired():
        finalize_exam_attempt(quiz, submission, {}, {})
        messages.error(request, "Time expired on this attempt; it has been submitted automatically.")
        return redirect("quiz_result", submission_id=submission.id)

    questions = quiz.questions.prefetch_related("choices").all()
    return render(request, "quizzes/exam_take.html", {
        "quiz": quiz,
        "questions": questions,
        "submission": submission,
    })


@login_required
def exam_integrity_event_view(request, submission_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    submission = get_object_or_404(
        Submission, id=submission_id, student=request.user, submitted_at__isnull=True,
    )
    event_type = request.POST.get("event_type", "")
    if event_type not in dict(ExamIntegrityEvent.EventType.choices):
        return HttpResponseBadRequest("Invalid event_type")

    ExamIntegrityEvent.objects.create(
        submission=submission, event_type=event_type, detail=request.POST.get("detail", "")[:255],
    )
    submission.flagged_for_review = True
    submission.save(update_fields=["flagged_for_review"])
    return JsonResponse({"ok": True})


@login_required
def exam_snapshot_upload_view(request, submission_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    submission = get_object_or_404(
        Submission, id=submission_id, student=request.user, submitted_at__isnull=True,
    )
    image = request.FILES.get("image")
    if not image:
        return HttpResponseBadRequest("Missing image")

    trigger = request.POST.get("trigger", ExamSnapshot.Trigger.INTERVAL)
    if trigger not in dict(ExamSnapshot.Trigger.choices):
        trigger = ExamSnapshot.Trigger.INTERVAL

    ExamSnapshot.objects.create(submission=submission, image=image, trigger=trigger)
    return JsonResponse({"ok": True})


@login_required
def quiz_take_view(request, quiz_id):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "Only students can take quizzes.")
        return redirect("home")

    quiz = get_object_or_404(Quiz, id=quiz_id, subject__school=request.school)

    if quiz.assessment_type == Quiz.AssessmentType.EXAM:
        return redirect("quiz_start", quiz_id=quiz.id)

    questions = quiz.questions.prefetch_related("choices").all()

    if quiz.status == Quiz.Status.DRAFT:
        messages.error(request, "This quiz hasn't been published by your teacher yet.")
        return redirect("dashboard")

    if quiz.offerings.exists() and not student_may_sit_exam(quiz, request.school_membership):
        messages.error(request, "This quiz is restricted to a class you are not part of.")
        return redirect("dashboard")

    if quiz.is_past_deadline():
        messages.error(request, "The deadline for this quiz has passed.")
        return redirect("quiz_start", quiz_id=quiz.id)

    attempts_used = Submission.objects.filter(quiz=quiz, student=request.user).count()
    if attempts_used >= quiz.max_attempts:
        messages.error(request, "You've used all your attempts for this quiz.")
        return redirect("quiz_start", quiz_id=quiz.id)
    if request.method == "POST":
        with transaction.atomic():
            submission = Submission.objects.create(quiz=quiz, student=request.user)

            correct_count = 0
            total_graded = 0
            answer_summaries = []

            for question in questions:
                answer_key = f"question_{question.id}"

                if question.question_type == Question.QuestionType.MULTIPLE_CHOICE:
                    total_graded += 1
                    selected_choice_id = request.POST.get(answer_key)
                    selected_choice = None
                    is_correct = False

                    if selected_choice_id:
                        selected_choice = Choice.objects.filter(id=selected_choice_id, question=question).first()
                        if selected_choice and selected_choice.is_correct:
                            is_correct = True
                            correct_count += 1

                    Answer.objects.create(
                        submission=submission,
                        question=question,
                        selected_choice=selected_choice,
                        is_correct=is_correct,
                    )
                    answer_summaries.append(f"Q: {question.text} | Correct: {is_correct}")
                else:
                    text_answer = request.POST.get(answer_key, "")
                    total_graded += 1

                    ai_result = grade_short_answer(question.text, text_answer, school=quiz.subject.school)
                    if ai_result["is_correct"]:
                        correct_count += 1

                    Answer.objects.create(
                        submission=submission,
                        question=question,
                        text_answer=text_answer,
                        is_correct=ai_result["is_correct"],
                        ai_feedback=ai_result["feedback"],
                    )
                    answer_summaries.append(f"Q: {question.text} | Correct: {ai_result['is_correct']}")

            score_percent = round((correct_count / total_graded) * 100, 1) if total_graded > 0 else None
            submission.score = score_percent

            overall_feedback = generate_submission_feedback(
                quiz.title, score_percent, answer_summaries, school=quiz.subject.school
            )
            submission.ai_feedback = overall_feedback
            submission.save()

            # Award badges
            if score_percent == 100:
                Badge.objects.get_or_create(
                    student=request.user, submission=submission, badge_type=Badge.BadgeType.PERFECT_SCORE
                )
            if attempts_used == 0 and score_percent is not None and score_percent >= 80:
                Badge.objects.get_or_create(
                    student=request.user, submission=submission, badge_type=Badge.BadgeType.FIRST_ATTEMPT
                )
            if attempts_used == 1:
                previous_submission = Submission.objects.filter(
                    quiz=quiz, student=request.user
                ).exclude(id=submission.id).order_by("submitted_at").first()
                if (previous_submission and previous_submission.score is not None
                        and score_percent is not None
                        and score_percent - previous_submission.score >= 20):
                    Badge.objects.get_or_create(
                        student=request.user, submission=submission, badge_type=Badge.BadgeType.IMPROVED
                    )

        messages.success(request, "Quiz submitted successfully!")
        return redirect("quiz_result", submission_id=submission.id)

    return render(request, "quizzes/quiz_take.html", {
        "quiz": quiz,
        "questions": questions,
    })


@login_required
def quiz_result_view(request, submission_id):
    submission = get_object_or_404(
        Submission,
        id=submission_id,
        student=request.user,
        quiz__subject__school=request.school,
    )
    quiz = submission.quiz
    answers = submission.answers.select_related("question", "selected_choice")

    attempts_used = Submission.objects.filter(quiz=quiz, student=request.user).count()
    attempts_remaining = quiz.max_attempts - attempts_used

    if quiz.assessment_type == Quiz.AssessmentType.EXAM:
        results_visible = submission.is_finished() and submission.score is not None and quiz.results_are_visible()
        return render(request, "quizzes/exam_result.html", {
            "quiz": quiz,
            "submission": submission,
            "answers": answers,
            "attempts_remaining": attempts_remaining,
            "results_visible": results_visible,
        })

    return render(request, "quizzes/quiz_result.html", {
        "submission": submission,
        "answers": answers,
        "attempts_remaining": attempts_remaining,
    })

@login_required
def quiz_create_choice_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "Only teachers can create quizzes.")
        return redirect("home")
    return render(request, "quizzes/quiz_create_choice.html")


@login_required
def create_quiz_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "Only teachers can create quizzes.")
        return redirect("home")

    if request.method == "POST":
        form = QuizForm(request.POST, school=request.school)
        if form.is_valid():
            quiz = form.save(commit=False)
            quiz.teacher = request.user
            quiz.save()
            messages.success(request, "Quiz created! Now add some questions.")
            return redirect("add_question", quiz_id=quiz.id)
    else:
        form = QuizForm(school=request.school)

    return render(request, "quizzes/create_quiz.html", {"form": form})


@login_required
def add_question_view(request, quiz_id):
    quiz = get_object_or_404(
        Quiz, id=quiz_id, teacher=request.user, subject__school=request.school
    )

    if request.method == "POST":
        question_form = QuestionForm(request.POST, quiz=quiz)
        choice_formset = ChoiceFormSet(request.POST, prefix="choices")

        if question_form.is_valid():
            question = question_form.save(commit=False)
            question.quiz = quiz
            question.save()

            if question.question_type == Question.QuestionType.MULTIPLE_CHOICE and choice_formset.is_valid():
                for choice_data in choice_formset.cleaned_data:
                    if choice_data.get("text"):
                        Choice.objects.create(
                            question=question,
                            text=choice_data["text"],
                            is_correct=choice_data.get("is_correct", False),
                        )

            messages.success(request, "Question added!")
            return redirect("add_question", quiz_id=quiz.id)
    else:
        question_form = QuestionForm(initial={"order": quiz.questions.count() + 1}, quiz=quiz)
        choice_formset = ChoiceFormSet(prefix="choices")

    return render(request, "quizzes/add_question.html", {
        "quiz": quiz,
        "question_form": question_form,
        "choice_formset": choice_formset,
        "existing_questions": quiz.questions.all(),
    })


def _exam_publish_error(quiz):
    questions = list(quiz.questions.all())
    if not questions:
        return "Add at least one question before publishing this exam."

    has_essay = any(q.question_type == Question.QuestionType.ESSAY for q in questions)
    has_objective = any(q.question_type != Question.QuestionType.ESSAY for q in questions)
    essay_weight = quiz.essay_weight_percent if quiz.essay_weight_percent is not None else Decimal("0")

    if has_essay and not has_objective and essay_weight < Decimal("100"):
        return "This exam has only essay questions - set the essay weight to 100."
    if has_essay and has_objective and essay_weight <= Decimal("0"):
        return "This exam has essay questions - set an essay weight greater than 0."
    if not has_essay and essay_weight > Decimal("0"):
        return "This exam has no essay questions - essay weight must be 0."
    if quiz.results_release_mode == Quiz.ResultsReleaseMode.SCHEDULED and not quiz.results_release_at:
        return "Set a results release time, or switch to manual/instant release."
    if not quiz.offerings.exists():
        return "Select at least one class to sit this exam before publishing."
    return None


@login_required
def publish_quiz_view(request, quiz_id):
    quiz = get_object_or_404(
        Quiz, id=quiz_id, teacher=request.user, subject__school=request.school
    )
    if request.method == "POST" and quiz.status == Quiz.Status.DRAFT:
        if quiz.assessment_type == Quiz.AssessmentType.EXAM:
            error = _exam_publish_error(quiz)
            if error:
                messages.error(request, error)
                return redirect("add_question", quiz_id=quiz.id)
        quiz.status = Quiz.Status.PUBLISHED
        quiz.save(update_fields=["status"])
        messages.success(request, "Quiz published - students can now take it.")
    return redirect("add_question", quiz_id=quiz.id)


@login_required
def select_exam_offerings_view(request, quiz_id):
    quiz = get_object_or_404(
        Quiz, id=quiz_id, teacher=request.user, subject__school=request.school,
    )
    if request.method == "POST":
        form = ExamOfferingsForm(
            request.POST, teacher_membership=request.school_membership, subject=quiz.subject,
        )
        if form.is_valid():
            quiz.offerings.set(form.cleaned_data["offerings"])
            messages.success(request, "Exam roster updated.")
            return redirect("add_question", quiz_id=quiz.id)
    else:
        form = ExamOfferingsForm(
            teacher_membership=request.school_membership, subject=quiz.subject,
            initial={"offerings": quiz.offerings.all()},
        )

    return render(request, "quizzes/select_exam_offerings.html", {"quiz": quiz, "form": form})


@login_required
def exam_roster_view(request, quiz_id):
    if not has_school_role(request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied

    quiz = get_object_or_404(
        Quiz, id=quiz_id, subject__school=request.school, assessment_type=Quiz.AssessmentType.EXAM,
    )
    is_admin = has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN)
    waivers = {w.student_id: w for w in quiz.fee_waivers.select_related("granted_by__user")}
    students = eligible_students_for_exam(quiz).select_related("user").order_by("user__username")

    roster = []
    for student in students:
        waiver = waivers.get(student.id)
        balance = Decimal("0") if waiver else get_fee_balance(student)
        roster.append({"student": student, "balance": balance, "waiver": waiver})

    return render(request, "quizzes/exam_roster.html", {
        "quiz": quiz, "roster": roster, "is_admin": is_admin,
    })


@login_required
def grant_exam_fee_waiver_view(request, quiz_id, student_id):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied

    quiz = get_object_or_404(
        Quiz, id=quiz_id, subject__school=request.school, assessment_type=Quiz.AssessmentType.EXAM,
    )
    student = get_object_or_404(
        SchoolMembership, id=student_id, school=request.school, role=SchoolMembership.Role.STUDENT,
    )
    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "A reason is required to grant a fee waiver.")
        elif ExamFeeWaiver.objects.filter(student=student, quiz=quiz).exists():
            messages.error(request, "This student already has a waiver for this exam.")
        else:
            ExamFeeWaiver.objects.create(
                student=student, quiz=quiz, granted_by=request.school_membership, reason=reason,
            )
            messages.success(request, f"Fee waiver granted for {student.user.username}.")
    return redirect("exam_roster", quiz_id=quiz.id)


@login_required
def exam_grading_queue_view(request, quiz_id):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "Only teachers can grade exams.")
        return redirect("home")

    quiz = get_object_or_404(
        Quiz, id=quiz_id, teacher=request.user, subject__school=request.school,
        assessment_type=Quiz.AssessmentType.EXAM,
    )
    pending_ids = Submission.objects.filter(
        quiz=quiz, submitted_at__isnull=False,
        answers__question__question_type=Question.QuestionType.ESSAY,
        answers__points_awarded__isnull=True,
    ).values_list("id", flat=True).distinct()
    pending_submissions = Submission.objects.filter(id__in=pending_ids).select_related("student").order_by("submitted_at")
    graded_submissions = Submission.objects.filter(
        quiz=quiz, submitted_at__isnull=False,
    ).exclude(id__in=pending_ids).select_related("student").order_by("-submitted_at")

    return render(request, "quizzes/exam_grading_queue.html", {
        "quiz": quiz,
        "pending_submissions": pending_submissions,
        "graded_submissions": graded_submissions,
    })


@login_required
def exam_attempt_detail_view(request, submission_id):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "Only teachers can grade exams.")
        return redirect("home")

    submission = get_object_or_404(
        Submission, id=submission_id,
        quiz__teacher=request.user, quiz__subject__school=request.school,
        quiz__assessment_type=Quiz.AssessmentType.EXAM,
    )
    essay_answers = Answer.objects.filter(
        submission=submission, question__question_type=Question.QuestionType.ESSAY,
    ).select_related("question").order_by("question__order", "id")
    objective_answers = submission.answers.exclude(
        question__question_type=Question.QuestionType.ESSAY,
    ).select_related("question", "selected_choice").order_by("question__order", "id")

    if request.method == "POST":
        formset = EssayGradingFormSet(request.POST, queryset=essay_answers, prefix="essay")
        if formset.is_valid():
            now = timezone.now()
            for form in formset:
                if form.has_changed():
                    answer = form.save(commit=False)
                    answer.graded_at = now
                    answer.save()
            recompute_exam_score(submission)
            messages.success(request, "Grades saved.")
            return redirect("exam_grading_queue", quiz_id=submission.quiz.id)
    else:
        initial = [
            {} if answer.points_awarded is not None else {
                "points_awarded": answer.ai_suggested_points,
                "teacher_feedback": answer.ai_suggested_feedback,
            }
            for answer in essay_answers
        ]
        formset = EssayGradingFormSet(queryset=essay_answers, prefix="essay", initial=initial)

    return render(request, "quizzes/exam_attempt_detail.html", {
        "submission": submission,
        "formset": formset,
        "essay_answers": essay_answers,
        "objective_answers": objective_answers,
        "integrity_events": submission.integrity_events.all(),
        "snapshots": submission.snapshots.all(),
    })


@login_required
def clear_exam_flag_view(request, submission_id):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "Only teachers can review exam attempts.")
        return redirect("home")

    submission = get_object_or_404(
        Submission, id=submission_id,
        quiz__teacher=request.user, quiz__subject__school=request.school,
        quiz__assessment_type=Quiz.AssessmentType.EXAM,
    )
    if request.method == "POST":
        submission.flagged_for_review = False
        submission.save(update_fields=["flagged_for_review"])
        messages.success(request, "Marked as reviewed.")
    return redirect("exam_attempt_detail", submission_id=submission.id)


@login_required
def publish_exam_results_view(request, quiz_id):
    if not has_school_role(request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied

    quiz = get_object_or_404(
        Quiz, id=quiz_id, subject__school=request.school, assessment_type=Quiz.AssessmentType.EXAM,
    )
    if has_school_role(request, SchoolMembership.Role.TEACHER) and quiz.teacher_id != request.user.id:
        raise PermissionDenied

    if request.method == "POST":
        quiz.results_published_at = timezone.now()
        quiz.save(update_fields=["results_published_at"])
        messages.success(request, "Results published - students can now see their exam scores.")
    return redirect("exam_grading_queue", quiz_id=quiz.id)


@login_required
def quiz_generation_settings_view(request):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied

    settings_row, _ = QuizGenerationSettings.objects.get_or_create(school=request.school)

    if request.method == "POST":
        settings_row.require_review = request.POST.get("require_review") == "on"
        settings_row.save(update_fields=["require_review"])
        messages.success(request, "Quiz generation settings saved.")
        return redirect("quiz_generation_settings")

    return render(request, "quizzes/quiz_generation_settings.html", {"settings_row": settings_row})


@login_required
def ai_generate_quiz_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "Only teachers can create quizzes.")
        return redirect("home")

    if request.method == "POST":
        form = AIQuizGenerationForm(request.POST, school=request.school)
        if form.is_valid():
            settings_row = QuizGenerationSettings.objects.filter(school=request.school).first()
            require_review = settings_row.require_review if settings_row else True

            quiz = Quiz.objects.create(
                subject=form.cleaned_data["subject"],
                teacher=request.user,
                title=form.cleaned_data["title"],
                description=f"AI-generated quiz on: {form.cleaned_data['topic']}",
                status=Quiz.Status.DRAFT if require_review else Quiz.Status.PUBLISHED,
            )

            generated = generate_quiz_questions(
                form.cleaned_data["topic"],
                form.cleaned_data["num_questions"],
                form.cleaned_data["difficulty"],
                school=request.school,
            )

            if not generated:
                messages.error(request, "AI generation failed. Please try again or create manually.")
                quiz.delete()
                return redirect("ai_generate_quiz")

            for i, q_data in enumerate(generated, start=1):
                question = Question.objects.create(
                    quiz=quiz,
                    text=q_data["text"],
                    question_type=Question.QuestionType.MULTIPLE_CHOICE,
                    order=i,
                )
                for choice_data in q_data.get("choices", []):
                    Choice.objects.create(
                        question=question,
                        text=choice_data["text"],
                        is_correct=choice_data.get("is_correct", False),
                    )

            if require_review:
                messages.success(
                    request,
                    f"AI generated {len(generated)} questions as a draft. Review them, then "
                    "publish the quiz before students can take it.",
                )
            else:
                messages.success(request, f"AI generated {len(generated)} questions and published the quiz.")
            return redirect("add_question", quiz_id=quiz.id)
    else:
        form = AIQuizGenerationForm(school=request.school)

    return render(request, "quizzes/ai_generate_quiz.html", {"form": form})


@login_required
def generate_bank_questions_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "Only teachers can generate bank questions.")
        return redirect("home")

    if request.method == "POST":
        form = BankQuestionGenerationForm(request.POST, school=request.school)
        if form.is_valid():
            created = create_bank_questions(
                subject=form.cleaned_data["subject"],
                topic=form.cleaned_data["mastery_topic"],
                difficulty=form.cleaned_data["difficulty"],
                topic_description=form.cleaned_data["topic_description"],
                num_questions=form.cleaned_data["num_questions"],
                created_by=request.user,
            )

            if not created:
                messages.error(request, "AI generation failed. Please try again.")
                return redirect("generate_bank_questions")

            messages.success(
                request,
                f"Generated {len(created)} questions into the bank, pending review.",
            )
            return redirect("bank_review_queue")
    else:
        form = BankQuestionGenerationForm(school=request.school)

    return render(request, "quizzes/generate_bank_questions.html", {"form": form})


@login_required
def bank_review_queue_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied

    if request.method == "POST":
        bank_question = get_object_or_404(
            BankQuestion, pk=request.POST.get("bank_question_id"), subject__school=request.school,
        )
        action = request.POST.get("action")
        if action in ("approve", "reject"):
            bank_question.status = (
                BankQuestion.Status.APPROVED if action == "approve" else BankQuestion.Status.REJECTED
            )
            bank_question.review_note = request.POST.get("review_note", "")
            bank_question.reviewed_by = request.school_membership
            bank_question.reviewed_at = timezone.now()
            bank_question.save(update_fields=["status", "review_note", "reviewed_by", "reviewed_at"])
            messages.success(request, "Bank question updated.")
        return redirect("bank_review_queue")

    pending_questions = BankQuestion.objects.filter(
        subject__school=request.school, status=BankQuestion.Status.PENDING_REVIEW,
    ).select_related("subject", "topic__strand").prefetch_related("choices")

    return render(request, "quizzes/bank_review_queue.html", {"pending_questions": pending_questions})


@login_required
def add_bank_questions_view(request, quiz_id):
    quiz = get_object_or_404(
        Quiz, id=quiz_id, teacher=request.user, subject__school=request.school
    )

    bank_filter = {"subject": quiz.subject, "status": BankQuestion.Status.APPROVED}
    if quiz.assessment_type != Quiz.AssessmentType.EXAM:
        bank_filter["question_type__in"] = [
            choice for choice, _ in Question.QuestionType.choices if choice != Question.QuestionType.ESSAY
        ]

    if request.method == "POST":
        selected_ids = request.POST.getlist("bank_question_id")
        bank_questions = BankQuestion.objects.filter(
            pk__in=selected_ids, **bank_filter,
        ).prefetch_related("choices")

        next_order = quiz.questions.count() + 1
        added = 0
        for bank_question in bank_questions:
            question = Question.objects.create(
                quiz=quiz,
                text=bank_question.text,
                question_type=bank_question.question_type,
                order=next_order,
                topic=bank_question.topic,
            )
            for choice in bank_question.choices.all():
                Choice.objects.create(
                    question=question, text=choice.text, is_correct=choice.is_correct,
                )
            next_order += 1
            added += 1

        if added:
            messages.success(request, f"Added {added} question(s) from the bank.")
        return redirect("add_question", quiz_id=quiz.id)

    approved_questions = BankQuestion.objects.filter(
        **bank_filter,
    ).select_related("topic__strand").prefetch_related("choices")

    return render(request, "quizzes/add_bank_questions.html", {
        "quiz": quiz, "approved_questions": approved_questions,
    })


@login_required
def create_assignment_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "Only teachers can create assignments.")
        return redirect("home")

    if request.method == "POST":
        form = AssignmentForm(request.POST, school=request.school)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.teacher = request.user
            assignment.save()
            messages.success(request, "Assignment created! Now build a grading rubric (optional).")
            return redirect("manage_rubric", assignment_id=assignment.id)
    else:
        form = AssignmentForm(school=request.school)

    return render(request, "quizzes/create_assignment.html", {"form": form})


@login_required
def manage_rubric_view(request, assignment_id):
    assignment = get_object_or_404(
        Assignment, id=assignment_id, teacher=request.user, subject__school=request.school
    )

    if request.method == "POST":
        formset = RubricCriterionFormSet(request.POST, instance=assignment)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Rubric saved.")
            return redirect("manage_rubric", assignment_id=assignment.id)
    else:
        formset = RubricCriterionFormSet(instance=assignment)

    return render(request, "quizzes/manage_rubric.html", {"assignment": assignment, "formset": formset})


@login_required
def assignment_detail_view(request, assignment_id):
    assignment = get_object_or_404(
        Assignment, id=assignment_id, subject__school=request.school
    )
    is_student = has_school_role(request, SchoolMembership.Role.STUDENT)
    is_enrolled = assignment.subject.enrollments.filter(student=request.user).exists() if is_student else True

    if not is_enrolled:
        messages.error(request, "You need to enroll in this subject first.")
        return redirect("browse_subjects")

    my_submission = None
    if is_student:
        my_submission = AssignmentSubmission.objects.filter(
            assignment=assignment, student=request.user
        ).order_by("-submitted_at").first()

    if request.method == "POST" and is_student:
        if assignment.is_past_deadline():
            messages.error(request, "The deadline for this assignment has passed.")
            return redirect("assignment_detail", assignment_id=assignment.id)

        form = AssignmentSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                submission = form.save(commit=False)
                submission.assignment = assignment
                submission.student = request.user
                submission.save()

                criteria = list(assignment.criteria.all())
                if criteria:
                    submission.max_score = sum(c.max_points for c in criteria)
                    extracted_text = extract_text_from_file(submission.file)
                    ai_result = suggest_assignment_grade(
                        assignment.title, assignment.instructions, criteria,
                        extracted_text, submission.max_score,
                        school=assignment.subject.school,
                    )
                    created_scores = [
                        CriterionScore.objects.create(
                            submission=submission, criterion=criterion,
                            ai_score=result.get("score"), ai_feedback=result.get("feedback", ""),
                        )
                        for criterion, result in zip(criteria, ai_result["criteria"])
                    ]
                    scored = [cs.ai_score for cs in created_scores if cs.ai_score is not None]
                    submission.ai_suggested_score = sum(scored) if scored else None
                    submission.ai_suggested_feedback = ai_result["overall_feedback"]
                    submission.save()

            messages.success(request, "Assignment submitted successfully!")
            return redirect("assignment_detail", assignment_id=assignment.id)
    else:
        form = AssignmentSubmissionForm()

    return render(request, "quizzes/assignment_detail.html", {
        "assignment": assignment,
        "form": form,
        "my_submission": my_submission,
    })


@login_required
def assignment_submissions_list_view(request, assignment_id):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "Only teachers can view submissions.")
        return redirect("home")

    assignment = get_object_or_404(
        Assignment,
        id=assignment_id,
        teacher=request.user,
        subject__school=request.school,
    )
    submissions = assignment.submissions.select_related("student").order_by("-submitted_at")

    return render(request, "quizzes/assignment_submissions_list.html", {
        "assignment": assignment,
        "submissions": submissions,
    })


@login_required
def grade_assignment_view(request, submission_id):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "Only teachers can grade assignments.")
        return redirect("home")

    submission = get_object_or_404(
        AssignmentSubmission,
        id=submission_id,
        assignment__teacher=request.user,
        assignment__subject__school=request.school,
    )

    if request.method == "POST":
        form = GradeAssignmentForm(request.POST, instance=submission)
        if form.is_valid():
            from django.utils import timezone
            graded_submission = form.save(commit=False)
            graded_submission.graded_at = timezone.now()
            graded_submission.save()
            messages.success(request, "Grade submitted successfully!")
            return redirect("assignment_submissions_list", assignment_id=submission.assignment.id)
    else:
        initial = {}
        if submission.ai_suggested_score is not None:
            initial["final_score"] = submission.ai_suggested_score
        if submission.ai_suggested_feedback:
            initial["teacher_feedback"] = submission.ai_suggested_feedback
        form = GradeAssignmentForm(instance=submission, initial=initial)

    return render(request, "quizzes/grade_assignment.html", {
        "submission": submission,
        "form": form,
        "criterion_scores": submission.criterion_scores.select_related("criterion"),
    })
