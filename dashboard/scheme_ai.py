from ai_core.client import AIError, complete_json


def generate_demo_scheme(*, subject_name, class_level, term, num_weeks, **kwargs):
    """Deterministic synthetic scheme when the hosted demo has no AI credentials."""
    return {
        "weeks": [
            {"week": week, "topic": f"{subject_name} topic {week} for {class_level} ({term})"}
            for week in range(1, num_weeks + 1)
        ],
    }


def generate_scheme_of_learning(class_level, subject_name, term, num_weeks, starting_topics="", *, school=None):
    """Returns a dict: {"weeks": [{"week": 1, "topic": "..."}, ...]}"""
    prompt = f"""You are an experienced teacher creating a term's Scheme of Learning following the Ghana Education Service (GES) standards-based curriculum format - a week-by-week table of topics for one term.

Details:
- Class: {class_level}
- Subject: {subject_name}
- Term: {term}
- Number of weeks: {num_weeks}
- Starting topics (if provided, continue logically from these; otherwise plan a sensible progression from the beginning of the term): {starting_topics or "Not specified - plan a logical progression for this subject and class level"}

Respond ONLY with valid JSON in this exact structure, nothing else - no markdown formatting, no code fences, no preamble:

{{
  "weeks": [
    {{"week": 1, "topic": "short topic name for week 1"}}
  ]
}}

Include exactly {num_weeks} week entries, numbered 1 to {num_weeks}. Topics must build logically week to week, appropriate for {class_level}. Keep each topic name short (a few words), matching how topics are named in a real GES scheme of learning."""

    try:
        return complete_json(prompt, max_tokens=2000, school=school, source="scheme_of_learning")
    except AIError:
        return None
