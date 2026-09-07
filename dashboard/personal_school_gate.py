"""Gates AI content generation for independent teachers (personal schools)
behind a free-generation allowance, then a monthly fair-use ceiling once
paid, routing to a payable invoice only while still on the free allowance.
Real institutions are never affected - every check here short-circuits to
"allowed" unless request.school.is_personal.
"""
from datetime import timedelta

from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from ai_core.models import AIUsageEvent

FREE_GENERATION_LIMIT = 6
# A paid ACTIVE license isn't unlimited - sized so that even the heaviest
# realistic month of use stays well under the plan's price in raw AI cost
# (the daily token cap alone isn't the right lever for this: it exists to
# stop single-day bursts, and setting it low enough to bound a *month* of
# steady use would block a normal single prep session).
PAID_MONTHLY_GENERATION_LIMIT = 30
GENERATION_SOURCES = (
    AIUsageEvent.Source.LESSON_AI,
    AIUsageEvent.Source.SCHEME_OF_LEARNING,
    AIUsageEvent.Source.STUDENT_NOTES,
)


def _generation_count(school, *, since=None):
    events = AIUsageEvent.objects.filter(school=school, source__in=GENERATION_SOURCES, succeeded=True)
    if since:
        events = events.filter(created_at__date__gte=since)
    return events.count()


def generation_allowed(request):
    """True unless this is a personal school that's used its free
    generations (FREE_GENERATION_LIMIT, across all document types) with no
    paid license, or has hit its monthly fair-use ceiling
    (PAID_MONTHLY_GENERATION_LIMIT) with one."""
    school = request.school
    if not school or not school.is_personal:
        return True

    from billing.models import SchoolLicense

    license = SchoolLicense.objects.filter(school=school).first()
    if license and license.status == SchoolLicense.Status.ACTIVE:
        return _generation_count(school, since=license.current_period_start) < PAID_MONTHLY_GENERATION_LIMIT

    return _generation_count(school) < FREE_GENERATION_LIMIT


def paid_monthly_limit_reached(request):
    """True only for an ACTIVE-license personal school that has hit its
    monthly fair-use ceiling - distinct from the free trial being
    exhausted, since there's nothing to pay for in this case. Callers use
    this to show a "resets next period" message instead of sending an
    already-paying teacher back through invoice payment."""
    school = request.school
    if not school or not school.is_personal:
        return False

    from billing.models import SchoolLicense

    license = SchoolLicense.objects.filter(school=school).first()
    if not (license and license.status == SchoolLicense.Status.ACTIVE):
        return False
    return _generation_count(school, since=license.current_period_start) >= PAID_MONTHLY_GENERATION_LIMIT


def subscribe_redirect_url(request):
    """Generates (on demand, rather than waiting for the periodic billing
    job) a payable invoice for this personal school and returns the URL to
    pay it. Shared by redirect_to_subscribe (full-page redirect) and the
    async JSON generation-gate response, which needs the same URL string
    to hand back to client-side JS.
    """
    from billing.models import LicenseInvoice, SchoolLicense
    from billing.services import generate_invoice

    license = SchoolLicense.objects.get(school=request.school)
    invoice = LicenseInvoice.objects.filter(
        license=license, status=LicenseInvoice.Status.PENDING
    ).order_by("-created_at").first()
    if not invoice:
        today = timezone.localdate()
        invoice = generate_invoice(
            school_license=license, period_start=today, period_end=today + timedelta(days=30),
        )
    return reverse("billing_pay_invoice", args=[invoice.pk])


def redirect_to_subscribe(request):
    """Sends the teacher to pay for a personal-school license (full-page
    redirect - see subscribe_redirect_url for the async JSON equivalent)."""
    return redirect(subscribe_redirect_url(request))
