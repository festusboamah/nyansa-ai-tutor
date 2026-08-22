from pypdf import PdfReader

from ai_core.client import AIError, complete_json


def extract_text_from_file(file_field):
    """
    Extracts text from an uploaded file. Currently supports PDF.
    Returns empty string if extraction fails or file type isn't supported.
    """
    try:
        file_field.seek(0)
        reader = PdfReader(file_field)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts).strip()
    except Exception:
        return ""


def suggest_assignment_grade(assignment_title, instructions, criteria, student_text, max_score):
    """
    `criteria` is an iterable of objects with .name/.description/.max_points.
    Returns a dict: {"criteria": [{"score": float, "feedback": str}, ...], "overall_feedback": str}
    The "criteria" list is always positionally aligned with the input `criteria`.
    """
    criteria = list(criteria)

    if not criteria:
        return {"criteria": [], "overall_feedback": "No rubric criteria defined."}

    if not student_text.strip():
        return {
            "criteria": [{"score": None, "feedback": "Could not extract readable text."} for _ in criteria],
            "overall_feedback": "Could not extract readable text from this submission. Manual review needed.",
        }

    truncated_text = student_text[:12000]

    criteria_description = "\n".join(
        f"{i + 1}. {c.name} (max {c.max_points} points): {c.description or 'No further description.'}"
        for i, c in enumerate(criteria)
    )

    prompt = f"""You are assisting a teacher in grading a student assignment submission against a rubric. Your suggestion will be reviewed by the teacher before being finalized - you are not making the final decision.

Assignment: {assignment_title}
Instructions: {instructions}
Maximum possible score: {max_score}

Grading rubric ({len(criteria)} criteria, in order):
{criteria_description}

Student's submission (extracted text):
{truncated_text}

Evaluate this submission against EACH criterion above, in the same order. Respond ONLY with valid JSON in this exact format, nothing else:
{{
  "criteria": [
    {{"score": "a number between 0 and that criterion's max points", "feedback": "1-2 sentences specific to this criterion"}}
  ],
  "overall_feedback": "2-3 sentences summarizing strengths and areas for improvement across the whole submission"
}}
The "criteria" array must have exactly {len(criteria)} entries, in the same order as the rubric above."""

    try:
        result = complete_json(prompt, max_tokens=800)
        return {
            "criteria": [
                {"score": item.get("score"), "feedback": item.get("feedback", "")}
                for item in result.get("criteria", [])
            ],
            "overall_feedback": result.get("overall_feedback", ""),
        }
    except AIError:
        return {
            "criteria": [{"score": None, "feedback": "AI suggestion unavailable."} for _ in criteria],
            "overall_feedback": "AI suggestion unavailable. Please grade manually.",
        }