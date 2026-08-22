from ai_core.client import AIError, complete_json


def generate_demo_lesson_note(*, subject_name, strand_topic, learning_indicator, resources, num_days, **kwargs):
    """Create a deterministic synthetic plan when the hosted demo has no AI credentials."""
    day_names = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
    return {
        "content_standard": f"Demonstrate understanding of {strand_topic} in {subject_name}.",
        "performance_indicators": learning_indicator,
        "resources": resources or "Chalkboard; learner notebooks; locally available teaching materials",
        "days": [
            {
                "day": day_names[index % len(day_names)],
                "starter": f"Review prior knowledge and introduce {strand_topic} with a familiar example.",
                "main": f"Guide learners through a structured {subject_name} activity on {strand_topic}. Model the task, let learners practise in pairs, then discuss evidence of understanding as a class.",
                "reflection": f"Ask learners to explain one idea about {strand_topic} and record what needs reinforcement.",
            }
            for index in range(num_days)
        ],
    }


def generate_lesson_note(class_level, subject_name, week_ending, strand_topic,
                          content_standard, learning_indicator, performance_indicator,
                          reference, resources, num_days, *, school=None):
    """
    Returns a dict: {"header": {...}, "days": [{"day": "Monday", "starter": "...", "main": "...", "reflection": "..."}, ...]}
    """
    prompt = f"""You are an experienced teacher creating a weekly lesson plan following the Ghana Education Service (GES) standards-based curriculum format.

Details:
- Class: {class_level}
- Subject: {subject_name}
- Week Ending: {week_ending}
- Strand/Topic: {strand_topic}
- Content Standard: {content_standard or "Not specified - infer a reasonable one from the topic"}
- Learning Indicator(s): {learning_indicator}
- Performance Indicator(s): {performance_indicator or "Infer reasonable performance indicators"}
- Reference: {reference or "Standard curriculum textbook"}
- Teaching/Learning Resources: {resources or "Standard classroom resources"}
- Number of days to plan: {num_days}

Respond ONLY with valid JSON in this exact structure, nothing else - no markdown formatting, no code fences, no preamble:

{{
  "content_standard": "the content standard, written out fully",
  "performance_indicators": "performance indicators as a single string, semicolon separated",
  "resources": "resources as a single string, semicolon separated",
  "days": [
    {{
      "day": "Monday",
      "starter": "concise starter activity, 2-4 sentences",
      "main": "detailed main activity for {class_level} on {strand_topic}, 4-8 sentences with concrete steps",
      "reflection": "concise reflection/closure activity, 2-3 sentences, including evidence of understanding to look for"
    }}
  ]
}}

Include exactly {num_days} day entries (starting Monday). Each day's content must be specific and practical for {class_level} on the topic "{strand_topic}", building logically day to day. Keep each field's text plain (no markdown, no bullet symbols) since it will be placed directly into table cells."""

    try:
        return complete_json(prompt, max_tokens=3000, school=school, source="lesson_ai")
    except AIError:
        return None
