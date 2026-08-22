from decimal import Decimal

# USD per million tokens. Update when Anthropic's published pricing changes -
# cost is computed live from this table, never frozen at call time, so a
# correction here applies to historical AIUsageEvent rows too.
MODEL_PRICING = {
    "claude-sonnet-4-5": {"input": Decimal("3.00"), "output": Decimal("15.00")},
}

ONE_MILLION = Decimal("1000000")


def estimate_cost(model, input_tokens, output_tokens):
    """
    Returns an estimated USD cost for a completed AI call, or None if the
    model isn't in MODEL_PRICING or token counts are missing - we don't
    guess at a number we can't actually support.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None or input_tokens is None or output_tokens is None:
        return None
    input_cost = (Decimal(input_tokens) / ONE_MILLION) * pricing["input"]
    output_cost = (Decimal(output_tokens) / ONE_MILLION) * pricing["output"]
    return (input_cost + output_cost).quantize(Decimal("0.0001"))
