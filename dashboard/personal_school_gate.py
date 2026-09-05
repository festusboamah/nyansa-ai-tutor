"""Gates AI content generation for independent teachers (personal schools)
behind a 3-free-generation allowance, then routes to a payable invoice.
Real institutions are never affected - every check here short-circuits to
"allowed" unless request.school.is_personal.
"""
from datetime import timedelta

from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from ai_core.models import AIUsageEvent

FREE_GENERATION_LIMIT = 6
GENERATION_SOURCES = (
    AIUsageEvent.Source.LESSON_AI,
    AIUsageEvent.Source.SCHEME_OF_LEARNING,
    AIUsageEvent.Source.STUDENT_NOTES,
)


def generation_allowed(request):
    """True unless this is a personal school that's used its free
    generations (FREE_GENERATION_LIMIT, across all document types) and
    isn't on a paid license."""
    school = request.school
    if not school or not school.is_personal:
        return True

    from billing.models import SchoolLicense

    license = SchoolLicense.objects.filter(school=school).first()
    if license and license.status == SchoolLicense.Status.ACTIVE:
        return True

    used = AIUsageEvent.objects.filter(
        school=school, source__in=GENERATION_SOURCES, succeeded=True
    ).count()
    return used < FREE_GENERATION_LIMIT


def redirect_to_subscribe(request):
    """Sends the teacher to pay for a personal-school license, generating a
    payable invoice on demand rather than waiting for the periodic billing
    job (which only runs on a fixed schedule, not the moment usage runs out).
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
    return redirect(reverse("billing_pay_invoice", args=[invoice.pk]))
