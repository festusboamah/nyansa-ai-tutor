import json
import anthropic
from pypdf import PdfReader
from django.conf import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


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


def suggest_assignment_grade(assignment_title, instructions, rubric, student_text, max_score):
    """
    Returns a dict: {"score": float, "feedback": str}
    """
    if not student_text.strip():
        return {
            "score": None,
            "feedback": "Could not extract readable text from this submission. Manual review needed.",
        }

    truncated_text = student_text[:12000]

    prompt = f"""You are assisting a teacher in grading a student assignment submission. Your suggestion will be reviewed by the teacher before being finalized - you are not making the final decision.

Assignment: {assignment_title}
Instructions: {instructions}
Grading rubric: {rubric or "No specific rubric provided - use general academic standards appropriate for the assignment"}
Maximum possible score: {max_score}

Student's submission (extracted text):
{truncated_text}

Evaluate this submission and respond ONLY with valid JSON in this exact format, nothing else:
{{"score": a number between 0 and {max_score}, "feedback": "2-4 sentences of constructive, specific feedback covering strengths and areas for improvement"}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = response.content[0].text.strip()

        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        result = json.loads(raw_text)
        return {
            "score": result.get("score"),
            "feedback": result.get("feedback", ""),
        }
    except Exception:
        return {
            "score": None,
            "feedback": "AI suggestion unavailable. Please grade manually.",
        }