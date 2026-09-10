from ai_core.client import AIError, complete_json
from .curriculum import curriculum_pages, evidence_prompt, references, valid_codes, codes, valid_alignment, source_wording


def generate_demo_lesson_note(*, subject_name, strand_topic, learning_indicator, resources, teaching_days, week_number=1, **kwargs):
    """Create a deterministic synthetic plan when the hosted demo has no AI credentials."""
    return {
        "week": f"Week {week_number}",
        "content_standard": f"Demonstrate understanding of {strand_topic} in {subject_name}.",
        "learning_indicator": learning_indicator,
        "performance_indicators": learning_indicator,
        "core_competencies": "Communication and Collaboration; Critical Thinking and Problem Solving",
        "resources": resources or "Chalkboard; learner notebooks; locally available teaching materials",
        "days": [
            {
                "day": day,
                "starter": f"Review prior knowledge and introduce {strand_topic} with a familiar example.",
                "main": f"Guide learners through a structured {subject_name} activity on {strand_topic}. Model the task, let learners practise in pairs, then discuss evidence of understanding as a class.",
                "reflection": f"Ask learners to explain one idea about {strand_topic} and record what needs reinforcement.",
            }
            for day in teaching_days
        ],
    }


def generate_lesson_note(class_level, subject_name, week_ending, strand_topic,
                          content_standard, learning_indicator, performance_indicator,
                          reference, resources, teaching_days, *, week_number=1, sub_strand="",
                          core_competencies="", school=None):
    """
    Returns a dict: {"header": {...}, "days": [{"day": "Monday", "starter": "...", "main": "...", "reflection": "..."}, ...]}
    """
    pages = curriculum_pages(subject_name, class_level, " ".join([strand_topic, sub_strand, content_standard, learning_indicator]))
    prompt = f"""You are an experienced teacher creating a weekly lesson plan following the Ghana Education Service (GES) standards-based curriculum format.

Details:
- Class: {class_level}
- Subject: {subject_name}
- Week: Week {week_number}
- Week Ending: {week_ending}
- Strand: {strand_topic}
- Sub-Strand: {sub_strand or "Not specified - infer a reasonable one from the strand"}
- Content Standard: {content_standard or "Select the matching standard from curriculum evidence; otherwise Curriculum reference required"}
- Learning Indicator(s): {learning_indicator or "Select from curriculum evidence in code: description format; otherwise Curriculum reference required"}
- Performance Indicator(s): {performance_indicator or "Infer reasonable performance indicators"}
- Core Competencies: {core_competencies or "Infer 2-4 relevant ones, e.g. Communication and Collaboration; Critical Thinking and Problem Solving; Personal Development; Creativity and Innovation"}
- Reference: {reference or "Standard curriculum textbook"}
- Teaching/Learning Resources: {resources or "Standard classroom resources"}
- Teaching Days: {", ".join(teaching_days)}

Respond ONLY with valid JSON in this exact structure, nothing else - no markdown formatting, no code fences, no preamble:

{{
  "week": "Week {week_number}",
  "content_standard": "the content standard, written out fully",
  "learning_indicator": "the indicator in '<code>: <description>' format",
  "performance_indicators": "performance indicators as a single string, semicolon separated",
  "core_competencies": "core competencies as a single string, semicolon separated",
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

Create one entry for each of these teaching days, in this exact order: {", ".join(teaching_days)}. Use these exact day names - do not add, remove, or rename any of them. Each day's content must be specific and practical for {class_level} on the topic "{strand_topic}", building logically day to day. Keep each field's text plain (no markdown, no bullet symbols) since it will be placed directly into table cells."""

    prompt += evidence_prompt(pages)
    try:
        result = complete_json(prompt, max_tokens=5000, school=school, source="lesson_ai")
        if not isinstance(result, dict) or not isinstance(result.get("days"), list):
            return None
        if len(result["days"]) != len(teaching_days):
            return None
        for day, expected in zip(result["days"], teaching_days):
            if not isinstance(day, dict) or day.get("day") != expected:
                return None
            if any(not isinstance(day.get(k), str) or not day[k].strip() or len(day[k]) > 6000 for k in ("starter", "main", "reflection")):
                return None
        if result.get("week") not in (None, f"Week {week_number}"):
            return None
        result["week"] = f"Week {week_number}"
        for field in ("content_standard", "learning_indicator", "performance_indicators", "core_competencies", "resources"):
            if not isinstance(result.get(field), str) or len(result[field]) > (300 if field in {"core_competencies", "resources"} else 4000):
                return None
        for text in (result["content_standard"], result["learning_indicator"], content_standard, learning_indicator):
            if codes(text) and not valid_codes(text, pages, class_level):
                return None
        if pages and any(not valid_codes(result[field], pages, class_level)
                         for field in ("content_standard", "learning_indicator")):
            return None
        if pages and not valid_alignment(result["content_standard"], result["learning_indicator"]):
            return None
        if pages and any(not source_wording(result[field], pages)
                         for field in ("content_standard", "learning_indicator")):
            return None
        result["curriculum_sources"] = references(pages)
        result["curriculum_warning"] = "Review curriculum wording and activities before use."
        if not pages:
            result["content_standard"] = content_standard or "Curriculum reference required"
            result["learning_indicator"] = learning_indicator or "Curriculum reference required"
            result["curriculum_warning"] = "No matching curriculum evidence in the supplied pack. Teacher-supplied references require verification."
        return result
    except AIError:
        return None
