from django.db import transaction
from django.utils import timezone

from .ai_grading import grade_short_answer, generate_submission_feedback
from .assignment_ai import extract_text_from_file
from .exam_ai import suggest_essay_grade
from .models import Answer, Choice, Question


def finalize_exam_attempt(quiz, submission, post_data, files_data=None):
    """
    Grades every question for an exam attempt from `post_data`/`files_data`
    (typically request.POST/request.FILES, or empty dicts to finalize an
    attempt with no answers - e.g. an expired, never-submitted attempt),
    creates the Answer rows, computes the combined score, and marks the
    submission finished. Caller must ensure submission.is_finished() is False.
    """
    files_data = files_data or {}
    questions = quiz.questions.prefetch_related("choices").all()
    answer_summaries = []
    has_essay = False

    with transaction.atomic():
        for question in questions:
            answer_key = f"question_{question.id}"

            if question.question_type == Question.QuestionType.MULTIPLE_CHOICE:
                selected_choice_id = post_data.get(answer_key)
                selected_choice = None
                is_correct = False
                if selected_choice_id:
                    selected_choice = Choice.objects.filter(id=selected_choice_id, question=question).first()
                    if selected_choice and selected_choice.is_correct:
                        is_correct = True
                Answer.objects.create(
                    submission=submission, question=question,
                    selected_choice=selected_choice, is_correct=is_correct,
                )
                answer_summaries.append(f"Q: {question.text} | Correct: {is_correct}")

            elif question.question_type == Question.QuestionType.SHORT_ANSWER:
                text_answer = post_data.get(answer_key, "")
                ai_result = grade_short_answer(question.text, text_answer, school=quiz.subject.school)
                Answer.objects.create(
                    submission=submission, question=question, text_answer=text_answer,
                    is_correct=ai_result["is_correct"], ai_feedback=ai_result["feedback"],
                )
                answer_summaries.append(f"Q: {question.text} | Correct: {ai_result['is_correct']}")

            else:  # ESSAY
                has_essay = True
                text_answer = post_data.get(answer_key, "")
                uploaded_file = files_data.get(answer_key) if hasattr(files_data, "get") else None
                extracted_text = text_answer
                if uploaded_file:
                    extracted_text = extract_text_from_file(uploaded_file) or text_answer
                ai_result = suggest_essay_grade(
                    question.text, extracted_text, question.points, school=quiz.subject.school
                )
                Answer.objects.create(
                    submission=submission, question=question, text_answer=text_answer,
                    file_answer=uploaded_file, ai_suggested_points=ai_result["points"],
                    ai_suggested_feedback=ai_result["feedback"],
                )

        submission.submitted_at = timezone.now()
        submission.save(update_fields=["submitted_at"])

    recompute_exam_score(submission)

    if not has_essay:
        submission.refresh_from_db(fields=["score"])
        overall_feedback = generate_submission_feedback(
            quiz.title, submission.score, answer_summaries, school=quiz.subject.school
        )
        submission.ai_feedback = overall_feedback
        submission.save(update_fields=["ai_feedback"])

    return submission


def recompute_exam_score(submission):
    """
    Recomputes submission.score from objective + essay answers, weighted by
    quiz.essay_weight_percent. If any essay answer is still ungraded
    (points_awarded is None), the combined score is left pending (None) until
    a teacher finishes grading every essay answer.
    """
    quiz = submission.quiz
    answers = list(submission.answers.select_related("question"))
    objective_answers = [a for a in answers if a.question.question_type != Question.QuestionType.ESSAY]
    essay_answers = [a for a in answers if a.question.question_type == Question.QuestionType.ESSAY]

    objective_max = sum(a.question.points for a in objective_answers)
    objective_earned = sum(a.question.points for a in objective_answers if a.is_correct)
    objective_percent = (objective_earned / objective_max * 100) if objective_max > 0 else None

    if not essay_answers:
        submission.score = round(objective_percent, 1) if objective_percent is not None else None
        submission.save(update_fields=["score"])
        return submission.score

    if any(a.points_awarded is None for a in essay_answers):
        submission.score = None
        submission.save(update_fields=["score"])
        return None

    essay_max = sum(a.question.points for a in essay_answers)
    essay_earned = sum(a.points_awarded for a in essay_answers)
    essay_percent = (essay_earned / essay_max * 100) if essay_max > 0 else 0.0

    essay_weight = float(quiz.essay_weight_percent) if quiz.essay_weight_percent is not None else 0.0
    objective_weight = float(quiz.objective_weight_percent)

    if objective_percent is None:
        combined = essay_percent
    else:
        combined = (objective_percent * objective_weight + essay_percent * essay_weight) / 100

    submission.score = round(combined, 1)
    submission.save(update_fields=["score"])
    return submission.score
