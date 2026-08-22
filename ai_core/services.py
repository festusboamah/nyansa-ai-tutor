import calendar
from datetime import date

from django.db.models import Count, Sum
from django.utils import timezone

from .models import AIUsageEvent
from .pricing import estimate_cost


def current_month_range():
    today = timezone.localdate()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return date(today.year, today.month, 1), date(today.year, today.month, last_day)


def school_ai_usage(school, start=None, end=None):
    """
    Aggregates AIUsageEvent rows for a school over [start, end], grouped by
    source. Cost is estimated live from the current pricing table, not
    frozen at call time.
    """
    if start is None or end is None:
        start, end = current_month_range()

    events = AIUsageEvent.objects.filter(
        school=school, created_at__date__gte=start, created_at__date__lte=end,
    )

    by_source = []
    total_calls = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = None

    rows = events.values("source", "model").annotate(
        calls=Count("id"),
        input_tokens=Sum("input_tokens"),
        output_tokens=Sum("output_tokens"),
    ).order_by("source")

    for row in rows:
        cost = estimate_cost(row["model"], row["input_tokens"], row["output_tokens"])
        entry = {
            "source": AIUsageEvent.Source(row["source"]).label,
            "model": row["model"],
            "calls": row["calls"],
            "input_tokens": row["input_tokens"] or 0,
            "output_tokens": row["output_tokens"] or 0,
            "cost": cost,
        }
        by_source.append(entry)
        total_calls += entry["calls"]
        total_input_tokens += entry["input_tokens"]
        total_output_tokens += entry["output_tokens"]
        if cost is not None:
            total_cost = (total_cost or 0) + cost

    return {
        "start": start,
        "end": end,
        "by_source": by_source,
        "total_calls": total_calls,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost": total_cost,
        "failed_calls": events.filter(succeeded=False).count(),
    }
