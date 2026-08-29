from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from ai_core.services import school_ai_usage
from schools.models import SchoolMembership
from schools.services import has_school_role

from .models import LicenseInvoice, LicensePayment, LicensePlan, SchoolLicense
from .services import TRIAL_LENGTH_DAYS, generate_invoice, initiate_license_payment, process_paystack_webhook


def _admin(request):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied


@login_required
def billing_dashboard_view(request):
    _admin(request)
    license = SchoolLicense.objects.filter(school=request.school).select_related("plan").first()
    invoices = LicenseInvoice.objects.filter(school=request.school).order_by("-period_start")[:12]
    usage = school_ai_usage(request.school) if license else None
    return render(request, "billing/dashboard.html", {
        "license": license,
        "invoices": invoices,
        "usage": usage,
    })


@login_required
def plans_view(request):
    _admin(request)
    if SchoolLicense.objects.filter(school=request.school).exists():
        return redirect("billing_dashboard")

    plans = LicensePlan.objects.filter(is_active=True)
    if request.method == "POST":
        plan = get_object_or_404(LicensePlan, pk=request.POST.get("plan_id"), is_active=True)
        today = timezone.localdate()
        SchoolLicense.objects.create(
            school=request.school, plan=plan, status=SchoolLicense.Status.TRIAL,
            current_period_start=today, current_period_end=today + timedelta(days=TRIAL_LENGTH_DAYS),
        )
        messages.success(request, f"Started a trial of the {plan.name} plan.")
        return redirect("billing_dashboard")

    return render(request, "billing/plans.html", {"plans": plans})


@login_required
def pay_invoice_view(request, invoice_id):
    _admin(request)
    invoice = get_object_or_404(LicenseInvoice, pk=invoice_id, school=request.school)
    try:
        payment = initiate_license_payment(
            invoice=invoice, initiated_by=request.school_membership,
            email=request.user.email, callback_url=request.build_absolute_uri(reverse("billing_payment_callback")),
        )
    except Exception as error:
        messages.error(request, f"Payment could not be initialized: {error}")
        return redirect("billing_dashboard")
    return redirect(payment.authorization_url)


@login_required
def payment_callback_view(request):
    reference = request.GET.get("reference", "")
    payment = LicensePayment.objects.filter(reference=reference, school=request.school).first()
    return render(request, "billing/payment_callback.html", {"payment": payment})


@csrf_exempt
def paystack_webhook_view(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    try:
        process_paystack_webhook(
            raw_body=request.body, signature=request.headers.get("x-paystack-signature", "")
        )
    except PermissionDenied:
        return JsonResponse({"detail": "Invalid signature"}, status=401)
    except (ValidationError, ValueError):
        return JsonResponse({"detail": "Invalid event"}, status=400)
    return JsonResponse({"status": "accepted"})
