from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import Quiz, Question, Choice, Submission, Answer


@login_required
def quiz_start_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    question_count = quiz.questions.count()
    return render(request, "quizzes/quiz_start.html", {
        "quiz": quiz,
        "question_count": question_count,
    })


@login_required
def quiz_take_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    questions = quiz.questions.prefetch_related("choices").all()

    if request.method == "POST":
        with transaction.atomic():
            submission = Submission.objects.create(quiz=quiz, student=request.user)

            correct_count = 0
            total_mcq = 0

            for question in questions:
                answer_key = f"question_{question.id}"

                if question.question_type == Question.QuestionType.MULTIPLE_CHOICE:
                    total_mcq += 1
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
                else:
                    text_answer = request.POST.get(answer_key, "")
                    Answer.objects.create(
                        submission=submission,
                        question=question,
                        text_answer=text_answer,
                    )

            if total_mcq > 0:
                score_percent = round((correct_count / total_mcq) * 100, 1)
            else:
                score_percent = None

            submission.score = score_percent
            submission.save()

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
    return render(request, "quizzes/quiz_result.html", {
        "submission": submission,
        "answers": answers,
    })