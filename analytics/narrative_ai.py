import json

from django.conf import settings

from ai_core.client import complete_text


def generate_ai_narrative(metrics, *, school=None):
    prompt = (
        "Draft a concise school analytics narrative using only the JSON metrics below. "
        "State the period and sources, distinguish missing data, do not infer causes, "
        "do not name students, and end by requiring human review.\n\n"
        + json.dumps(metrics, ensure_ascii=False)
    )
    return complete_text(
        prompt, max_tokens=500, model=settings.ANALYTICS_AI_MODEL,
        school=school, source="analytics_narrative",
    )
