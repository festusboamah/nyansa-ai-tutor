from ai_core.client import AIError, complete_json


def suggest_essay_grade(question_text, student_text, max_points, *, school=None):
    """
    AI-assisted grading suggestion for one exam essay answer.
    Returns a dict: {"points": float or None, "feedback": str}
    Never final - a teacher must confirm before it counts (see Answer.points_awarded).
    """
    if not student_text.strip():
        return {"points": None, "feedback": "No answer was provided."}

    truncated_text = student_text[:12000]

    prompt = f"""You are assisting a teacher in grading a student's essay answer on a school exam. Your suggestion will be reviewed by the teacher before being finalized - you are not making the final decision.

Question: {question_text}
Maximum points for this question: {max_points}

Student's answer:
{truncated_text}

Evaluate this answer. Respond ONLY with valid JSON in this exact format, nothing else:
{{"points": "a number between 0 and {max_points}", "feedback": "2-3 sentences of specific, constructive feedback for the teacher to review"}}"""

    try:
        result = complete_json(prompt, max_tokens=400, school=school, source="exam_essay_grading")
        return {
            "points": result.get("points"),
            "feedback": result.get("feedback", ""),
        }
    except AIError:
        return {
            "points": None,
            "feedback": "AI suggestion unavailable. Please grade manually.",
        }
