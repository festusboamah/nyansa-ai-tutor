"""Shared low-level Claude-calling plumbing for single-shot AI features.

Not for tutor/engine.py's conversational, multi-turn flow - that has its own
error handling and usage logging. This is for the single prompt in, single
result out call sites (quiz generation, grading suggestions, summaries, ...).
"""
import json
import logging

import anthropic
from django.conf import settings

logger = logging.getLogger("nyansa")

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


class AIError(Exception):
    """Raised when a Claude call fails or returns something unusable. Callers
    decide their own fallback - this never returns a partial/guessed result."""


def complete_text(prompt, *, max_tokens, model=None):
    try:
        response = client.messages.create(
            model=model or settings.NYANSA_AI_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        logger.warning("AI completion failed: %s", exc)
        raise AIError(str(exc)) from exc


def complete_json(prompt, *, max_tokens, model=None):
    raw_text = complete_text(prompt, max_tokens=max_tokens, model=model)

    stripped = raw_text
    if stripped.startswith("```"):
        stripped = stripped.split("```")[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        logger.warning("AI JSON completion could not be parsed: %s", exc)
        raise AIError(f"Could not parse AI response as JSON: {exc}") from exc
