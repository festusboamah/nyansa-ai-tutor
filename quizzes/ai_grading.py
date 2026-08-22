from ai_core.client import AIError, complete_json, complete_text


def grade_short_answer(question_text, student_answer):
    """
    Sends a short-answer question + student's response to Claude,
    and returns a dict: {"is_correct": bool, "feedback": str}
    """
    if not student_answer.strip():
        return {"is_correct": False, "feedback": "No answer was provided."}

    prompt = f"""You are grading a student's short-answer response for a quiz.

Question: {question_text}
Student's answer: {student_answer}

Evaluate whether the answer is substantially correct. Respond ONLY with valid JSON in this exact format, nothing else:
{{"is_correct": true or false, "feedback": "a short, encouraging, 1-2 sentence explanation for the student"}}
"""

    try:
        result = complete_json(prompt, max_tokens=200)
        return {
            "is_correct": result.get("is_correct", False),
            "feedback": result.get("feedback", "Answer recorded."),
        }
    except AIError:
        return {
            "is_correct": None,
            "feedback": "Your answer was saved, but automatic grading is temporarily unavailable. Your teacher will review it.",
        }


def generate_submission_feedback(quiz_title, score, answer_summaries):
    """
    Generates an overall encouraging summary feedback for the whole quiz submission.
    """
    summary_text = "\n".join(answer_summaries)

    prompt = f"""A student just completed a quiz titled "{quiz_title}" and scored {score}%.

Here is a breakdown of their answers:
{summary_text}

Write a short, encouraging 2-3 sentence overall summary for the student. Mention what they did well and one area to focus on if applicable. Keep it warm and motivating, suitable for a student-facing dashboard. Respond with ONLY the summary text, no preamble."""

    try:
        return complete_text(prompt, max_tokens=200)
    except AIError:
        return "Great effort completing this quiz! Keep practicing to strengthen your understanding."
