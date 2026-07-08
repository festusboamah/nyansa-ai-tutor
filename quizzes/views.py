from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import Quiz, Question, Choice, Submission, Answer, Badge
from .ai_grading import grade_short_answer, generate_submission_feedback


@login_required
def quiz_start_view(request, quiz_id):
    if not request.user.is_student():
        messages.error(request, "Only students can take quizzes.")
        return redirect("home")

    quiz = get_object_or_404(Quiz, id=quiz_id)
    question_count = quiz.questions.count()
    attempts_used = Submission.objects.filter(quiz=quiz, student=request.user).count()
    attempts_remaining = quiz.max_attempts - attempts_used

    return render(request, "quizzes/quiz_start.html", {
        "quiz": quiz,
        "question_count": question_count,
        "attempts_used": attempts_used,
        "attempts_remaining": attempts_remaining,
    })


@login_required
def quiz_take_view(request, quiz_id):
    if not request.user.is_student():
        messages.error(request, "Only students can take quizzes.")
        return redirect("home")

    quiz = get_object_or_404(Quiz, id=quiz_id)
    questions = quiz.questions.prefetch_related("choices").all()

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
    submission = get_object_or_404(Submission, id=submission_id, student=request.user)
    answers = submission.answers.select_related("question", "selected_choice")

    attempts_used = Submission.objects.filter(quiz=submission.quiz, student=request.user).count()
    attempts_remaining = submission.quiz.max_attempts - attempts_used

    return render(request, "quizzes/quiz_result.html", {
        "submission": submission,
        "answers": answers,
        "attempts_remaining": attempts_remaining,
    })