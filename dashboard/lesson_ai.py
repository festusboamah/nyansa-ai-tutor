import json
import anthropic
from django.conf import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def generate_lesson_note(class_level, subject_name, week_ending, strand_topic,
                          content_standard, learning_indicator, performance_indicator,
                          reference, resources, num_days):
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
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = response.content[0].text.strip()

        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        return json.loads(raw_text)
    except Exception:
        return None