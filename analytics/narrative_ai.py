import json

import anthropic
from django.conf import settings


def generate_ai_narrative(metrics):
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = (
        "Draft a concise school analytics narrative using only the JSON metrics below. "
        "State the period and sources, distinguish missing data, do not infer causes, "
        "do not name students, and end by requiring human review.\n\n"
        + json.dumps(metrics, ensure_ascii=False)
    )
    response = client.messages.create(
        model=settings.ANALYTICS_AI_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()

