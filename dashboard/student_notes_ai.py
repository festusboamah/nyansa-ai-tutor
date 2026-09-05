from ai_core.client import AIError, complete_json


def generate_demo_student_note(*, subject_name, topic, class_level, **kwargs):
    """Deterministic synthetic note when the hosted demo has no AI credentials."""
    return {
        "sections": [
            {
                "heading": f"What is {topic}?",
                "text": f"This section introduces {topic} in {subject_name} for {class_level} learners, "
                        "explained in simple, everyday language with a familiar example.",
            },
            {
                "heading": "Key points to remember",
                "text": f"A short summary of the main ideas about {topic} that {class_level} learners should copy into their notebooks.",
            },
        ],
    }


def generate_student_notes(class_level, subject_name, topic, *, school=None):
    """Returns a dict: {"sections": [{"heading": "...", "text": "..."}, ...]}
    Unlike the lesson note (written for the teacher to deliver), this is the
    content a teacher gives students to read or copy directly."""
    prompt = f"""You are an experienced teacher writing student-facing notes on a topic - the actual explanatory content a student would read or copy into their exercise book, not a lesson plan for the teacher.

Details:
- Class: {class_level}
- Subject: {subject_name}
- Topic: {topic}

Write clear, age-appropriate explanatory notes a {class_level} student could read and understand on their own: definitions, explanations, and simple examples, building from simple to more detailed ideas.

Respond ONLY with valid JSON in this exact structure, nothing else - no markdown formatting, no code fences, no preamble:

{{
  "sections": [
    {{"heading": "a short section heading", "text": "the explanatory content for this section, written directly to the student, 3-6 sentences, plain language appropriate for {class_level}"}}
  ]
}}

Include 3 to 6 sections that build logically from an introduction to more detail, ending with a short summary section. Keep the language plain (no markdown, no bullet symbols) since it will be placed directly into a document."""

    try:
        return complete_json(prompt, max_tokens=2500, school=school, source="student_notes")
    except AIError:
        return None
