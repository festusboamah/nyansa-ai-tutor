import os
import json
import anthropic
from django.conf import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def grade_short_answer(question_text, student_answer):
    """
    Sends a short-answer question + student's response to Claude,
    and returns a dict: {"is_correct": bool, "feedback": str}
    """
    prompt = f"""You are grading a student's short-answer response for a quiz.

Question: {question_text}
Student's answer: {student_answer}

Evaluate whether the answer is substantially correct. Respond ONLY with valid JSON in this exact format, nothing else:
{{"is_correct": true or false, "feedback": "a short, encouraging, 1-2 sentence explanation for the student"}}
"""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text.strip()

    try:
        result = json.loads(raw_text)
        return {
            "is_correct": result.get("is_correct", False),
            "feedback": result.get("feedback", "Answer recorded."),
        }
    except (json.JSONDecodeError, KeyError):
        return {"is_correct": None, "feedback": "Answer recorded, but could not be auto-graded."}


def generate_submission_feedback(quiz_title, score, answer_summaries):
    """
    Generates an overall encouraging summary feedback for the whole quiz submission.
    answer_summaries: list of strings like "Q: ... | Correct: True"
    """
    summary_text = "\n".join(answer_summaries)

    prompt = f"""A student just completed a quiz titled "{quiz_title}" and scored {score}%.

Here is a breakdown of their answers:
{summary_text}

Write a short, encouraging 2-3 sentence overall summary for the student. Mention what they did well and one area to focus on if applicable. Keep it warm and motivating, suitable for a student-facing dashboard. Respond with ONLY the summary text, no preamble."""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text.strip()