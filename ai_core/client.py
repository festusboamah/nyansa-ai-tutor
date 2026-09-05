"""Shared low-level Claude-calling plumbing for single-shot AI features.

Not for tutor/engine.py's conversational, multi-turn flow - that has its own
error handling and usage logging. This is for the single prompt in, single
result out call sites (quiz generation, grading suggestions, summaries, ...).
"""
import json
import logging

import anthropic
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger("nyansa")

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


class AIError(Exception):
    """Raised when a Claude call fails or returns something unusable. Callers
    decide their own fallback - this never returns a partial/guessed result."""


def _daily_tokens_used(school):
    from ai_core.models import AIUsageEvent

    totals = AIUsageEvent.objects.filter(
        school=school, created_at__date=timezone.localdate()
    ).aggregate(input_total=Sum("input_tokens"), output_total=Sum("output_tokens"))
    return (totals["input_total"] or 0) + (totals["output_total"] or 0)


def _daily_token_cap(school):
    if school.is_personal:
        return settings.AI_DAILY_TOKEN_CAP_PER_PERSONAL_SCHOOL
    return settings.AI_DAILY_TOKEN_CAP_PER_SCHOOL


def _log_usage(*, school, source, model, input_tokens=None, output_tokens=None, succeeded=True, error_message=""):
    from ai_core.models import AIUsageEvent

    AIUsageEvent.objects.create(
        school=school,
        source=source,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        succeeded=succeeded,
        error_message=error_message,
    )


def complete_text(prompt, *, max_tokens, model=None, school=None, source=None):
    resolved_model = model or settings.NYANSA_AI_MODEL

    if school is not None and _daily_tokens_used(school) >= _daily_token_cap(school):
        raise AIError("Daily AI usage limit reached for this school. Try again tomorrow.")

    try:
        response = client.messages.create(
            model=resolved_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        if school is not None:
            _log_usage(
                school=school, source=source, model=resolved_model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        return response.content[0].text.strip()
    except Exception as exc:
        logger.warning("AI completion failed: %s", exc)
        if school is not None:
            _log_usage(school=school, source=source, model=resolved_model, succeeded=False, error_message=str(exc))
        raise AIError(str(exc)) from exc


def complete_json(prompt, *, max_tokens, model=None, school=None, source=None):
    raw_text = complete_text(prompt, max_tokens=max_tokens, model=model, school=school, source=source)

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
