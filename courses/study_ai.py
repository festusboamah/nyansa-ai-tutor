import anthropic
from pypdf import PdfReader
from django.conf import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def extract_text_from_pdf(file_field):
    """
    Extracts readable text from an uploaded PDF file.
    """
    try:
        reader = PdfReader(file_field)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts).strip()
    except Exception:
        return ""


def generate_summary(extracted_text):
    """
    Sends extracted PDF text to Claude and returns a clear, structured summary.
    """
    if not extracted_text.strip():
        return "Could not extract readable text from this document. It may be a scanned image rather than text-based PDF."

    truncated_text = extracted_text[:15000]

    prompt = f"""A student uploaded a document to study from. Here is the extracted text:

{truncated_text}

Write a clear, well-organized summary of this document for a student. Include:
1. The main topic/subject
2. Key points, organized as a short bulleted list
3. Any important definitions or concepts to remember

Keep it concise but informative. Respond with ONLY the summary, no preamble."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception:
        return "Summary generation is temporarily unavailable. Please try again later."


def answer_question_about_document(extracted_text, question, previous_qa=None):
    """
    Answers a student's question using the document's content as context.
    previous_qa: optional list of (question, answer) tuples for conversation continuity.
    """
    truncated_text = extracted_text[:15000]

    history_text = ""
    if previous_qa:
        for q, a in previous_qa:
            history_text += f"\nPrevious Q: {q}\nPrevious A: {a}\n"

    prompt = f"""A student is studying from this document:

{truncated_text}

{history_text}

The student's new question: {question}

Answer clearly and helpfully, using only information from the document above. If the answer isn't in the document, say so honestly rather than making something up. Keep your answer focused and student-friendly."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception:
        return "Sorry, I couldn't process your question right now. Please try again."