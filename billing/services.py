import hashlib
import hmac
import json
import secrets
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from ai_core.services import school_ai_usage

from .gateways import PaystackGateway
from .models import BillingProviderEvent, LicenseInvoice, LicensePayment, SchoolLicense


@transaction.atomic
def generate_invoice(*, school_license, period_start, period_end):
    existing = LicenseInvoice.objects.filter(
        license=school_license, period_start=period_start, period_end=period_end
    ).first()
    if existing:
        return existing

    plan = school_license.plan
    base_amount = plan.base_price
    ai_usage_amount = None
    if plan.ai_usage_markup_percent is not None:
        usage = school_ai_usage(school_license.school, period_start, period_end)
        if usage["total_cost"] is not None:
            # ai_core.pricing estimates cost in USD; this invoice is in the
            # plan's own currency (GHS) - convert before adding the markup.
            markup = Decimal(1) + (plan.ai_usage_markup_percent / Decimal(100))
            usage_in_plan_currency = usage["total_cost"] * settings.AI_USAGE_USD_TO_GHS_RATE
            ai_usage_amount = (usage_in_plan_currency * markup).quantize(Decimal("0.01"))

    total_amount = base_amount + (ai_usage_amount or Decimal("0"))
    return LicenseInvoice.objects.create(
        school=school_license.school, license=school_license,
        period_start=period_start, period_end=period_end,
        base_amount=base_amount, ai_usage_amount=ai_usage_amount,
        total_amount=total_amount, currency=plan.currency,
    )


def initiate_license_payment(*, invoice, initiated_by, email, callback_url, gateway=None):
    # Deliberately not @transaction.atomic: the gateway call is an external
    # network request, and wrapping it in a transaction means the exception
    # path below (persisting UNKNOWN before re-raising) would get rolled back
    # along with everything else the moment the exception leaves this
    # function - silently losing the payment row instead of preserving it.
    if invoice.status == LicenseInvoice.Status.PAID:
        raise ValidationError("This invoice has already been paid.")
    reference = f"NYB-{invoice.school_id}-{secrets.token_hex(10)}"
    payment = LicensePayment(
        school=invoice.school, invoice=invoice, initiated_by=initiated_by,
        amount=invoice.total_amount, currency=invoice.currency,
        status=LicensePayment.Status.PENDING, provider="PAYSTACK",
        reference=reference, payer_email=email,
    )
    payment.full_clean()
    payment.save()
    try:
        result = (gateway or PaystackGateway()).initialize(
            reference=reference, amount=invoice.total_amount, email=email, callback_url=callback_url
        )
    except Exception:
        payment.status = LicensePayment.Status.UNKNOWN
        payment.save(update_fields=["status", "updated_at"])
        raise
    payment.authorization_url = result["authorization_url"]
    payment.provider_transaction_id = str(result.get("access_code", ""))
    payment.save(update_fields=["authorization_url", "provider_transaction_id", "updated_at"])
    return payment


@transaction.atomic
def process_paystack_webhook(*, raw_body, signature):
    expected = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode("utf-8"), raw_body, hashlib.sha512
    ).hexdigest()
    if not settings.PAYSTACK_SECRET_KEY or not hmac.compare_digest(expected, signature or ""):
        raise PermissionDenied("Invalid Paystack signature.")

    payload = json.loads(raw_body.decode("utf-8"))
    data = payload.get("data") or {}
    event_type = payload.get("event", "unknown")
    digest = hashlib.sha256(raw_body).hexdigest()
    event_id = f"{event_type}:{data.get('id') or digest}"

    existing = BillingProviderEvent.objects.filter(provider="PAYSTACK", event_id=event_id).first()
    if existing:
        return existing

    reference = str(data.get("reference", ""))
    payment = LicensePayment.objects.select_for_update().filter(provider="PAYSTACK", reference=reference).first()
    event = BillingProviderEvent.objects.create(
        provider="PAYSTACK", event_id=event_id, payment=payment, event_type=event_type,
        payload_digest=digest, signature_valid=True,
    )
    if not payment:
        return event

    provider_amount = Decimal(str(data.get("amount", 0))) / 100
    currency = data.get("currency", "")
    if provider_amount != payment.amount or currency != payment.currency:
        return event

    if event_type == "charge.success":
        if payment.status != LicensePayment.Status.SUCCESSFUL:
            payment.status = LicensePayment.Status.SUCCESSFUL
            payment.successful_at = timezone.now()
            payment.provider_transaction_id = str(data.get("id", ""))
            payment.save(update_fields=["status", "successful_at", "provider_transaction_id", "updated_at"])
            invoice = payment.invoice
            invoice.status = LicenseInvoice.Status.PAID
            invoice.save(update_fields=["status"])
            license = invoice.license
            if license.status in {SchoolLicense.Status.TRIAL, SchoolLicense.Status.PAST_DUE}:
                license.status = SchoolLicense.Status.ACTIVE
                license.save(update_fields=["status"])
        event.processed = True
        event.save(update_fields=["processed"])
    elif event_type in {"charge.failed", "transaction.failed"}:
        if payment.status == LicensePayment.Status.PENDING:
            payment.status = LicensePayment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
        event.processed = True
        event.save(update_fields=["processed"])
    return event
