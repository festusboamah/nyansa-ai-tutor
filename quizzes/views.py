from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import Quiz, Question, Choice, Submission, Answer, Badge
from .ai_grading import grade_short_answer, generate_submission_feedback
from .forms import QuizForm, QuestionForm, ChoiceFormSet, AIQuizGenerationForm
from .ai_quiz_generator import generate_quiz_questions
from .models import Assignment, AssignmentSubmission
from .assignment_forms import AssignmentForm, AssignmentSubmissionForm, GradeAssignmentForm
from .assignment_ai import extract_text_from_file, suggest_assignment_grade
from schools.models import SchoolMembership
from schools.services import has_school_role


@login_required
def quiz_start_view(request, quiz_id):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "Only students can take quizzes.")
        return redirect("home")

    quiz = get_object_or_404(Quiz, id=quiz_id, subject__school=request.school)
    question_count = quiz.questions.count()
    attempts_used = Submission.objects.filter(quiz=quiz, student=request.user).count()
    attempts_remaining = quiz.max_attempts - attempts_used

    return render(request, "quizzes/quiz_start.html", {
        "quiz": quiz,
        "question_count": question_count,
        "attempts_used": attempts_used,
        "attempts_remaining": attempts_remaining,
        "past_deadline": quiz.is_past_deadline(),
    })


@login_required
def quiz_take_view(request, quiz_id):
    if not has_school_role(request, SchoolMembership.Role.STUDENT):
        messages.error(request, "Only students can take quizzes.")
        return redirect("home")

    quiz = get_object_or_404(Quiz, id=quiz_id, subject__school=request.school)
    questions = quiz.questions.prefetch_related("choices").all()

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
                        selected_choice = Choice.objects.filter(id=selected_choice_id).first()
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

                    ai_result = grade_short_answer(question.text, text_answer)
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

            overall_feedback = generate_submission_feedback(quiz.title, score_percent, answer_summaries)
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
    answers = submission.answers.select_related("question", "selected_choice")

    attempts_used = Submission.objects.filter(quiz=submission.quiz, student=request.user).count()
    attempts_remaining = submission.quiz.max_attempts - attempts_used

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
        question_form = QuestionForm(request.POST)
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
        question_form = QuestionForm(initial={"order": quiz.questions.count() + 1})
        choice_formset = ChoiceFormSet(prefix="choices")

    return render(request, "quizzes/add_question.html", {
        "quiz": quiz,
        "question_form": question_form,
        "choice_formset": choice_formset,
        "existing_questions": quiz.questions.all(),
    })


@login_required
def ai_generate_quiz_view(request):
    if not has_school_role(request, SchoolMembership.Role.TEACHER):
        messages.error(request, "Only teachers can create quizzes.")
        return redirect("home")

    if request.method == "POST":
        form = AIQuizGenerationForm(request.POST, school=request.school)
        if form.is_valid():
            quiz = Quiz.objects.create(
                subject=form.cleaned_data["subject"],
                teacher=request.user,
                title=form.cleaned_data["title"],
                description=f"AI-generated quiz on: {form.cleaned_data['topic']}",
            )

            generated = generate_quiz_questions(
                form.cleaned_data["topic"],
                form.cleaned_data["num_questions"],
                form.cleaned_data["difficulty"],
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

            messages.success(request, f"AI generated {len(generated)} questions! Review them below.")
            return redirect("add_question", quiz_id=quiz.id)
    else:
        form = AIQuizGenerationForm(school=request.school)

    return render(request, "quizzes/ai_generate_quiz.html", {"form": form})

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
            messages.success(request, "Assignment created successfully!")
            return redirect("teacher_dashboard")
    else:
        form = AssignmentForm(school=request.school)

    return render(request, "quizzes/create_assignment.html", {"form": form})


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
            submission = form.save(commit=False)
            submission.assignment = assignment
            submission.student = request.user
            submission.save()

            extracted_text = extract_text_from_file(submission.file)
            ai_result = suggest_assignment_grade(
                assignment.title, assignment.instructions, assignment.grading_rubric,
                extracted_text, submission.max_score,
            )
            submission.ai_suggested_score = ai_result["score"]
            submission.ai_suggested_feedback = ai_result["feedback"]
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
    })
