import json
import anthropic
from django.conf import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def generate_quiz_questions(topic, num_questions, difficulty):
    """
    Returns a list of dicts like:
    [{"text": "...", "question_type": "MCQ", "choices": [{"text": "...", "is_correct": True}, ...]}, ...]
    """
    prompt = f"""You are creating quiz questions for a student learning platform.

Topic: {topic}
Number of questions: {num_questions}
Difficulty: {difficulty}

Generate {num_questions} multiple-choice questions on this topic, at {difficulty} difficulty.
Each question must have exactly 4 answer choices, with exactly one marked correct.

Respond ONLY with valid JSON in this exact structure, no other text:
{{
  "questions": [
    {{
      "text": "question text here",
      "choices": [
        {{"text": "choice 1", "is_correct": false}},
        {{"text": "choice 2", "is_correct": true}},
        {{"text": "choice 3", "is_correct": false}},
        {{"text": "choice 4", "is_correct": false}}
      ]
    }}
  ]
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = response.content[0].text.strip()

        # Strip markdown code fences if Claude added them
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        result = json.loads(raw_text)
        return result.get("questions", [])
    except Exception:
        return []