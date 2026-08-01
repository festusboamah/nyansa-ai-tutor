import hashlib
import hmac
import json
import secrets
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from academics.models import ClassEnrollment
from communications.models import MessageTemplate
from communications.services import enqueue_guardian_event, enqueue_message, ensure_default_templates
from guardians.models import GuardianLink
from schools.models import SchoolMembership

from .gateways import PaystackGateway
from .models import (
    Adjustment, Charge, FeeStructure, Payment, PaymentAllocation, ProviderEvent,
    Receipt, ReconciliationException,
)


def _require_admin(actor, school):
    if actor.school_id != school.id or actor.role != SchoolMembership.Role.SCHOOL_ADMIN or not actor.is_active:
        raise PermissionDenied("Only an active school administrator can manage finance records.")


@transaction.atomic
def activate_fee_structure(*, structure, actor):
    _require_admin(actor, structure.school)
    structure = FeeStructure.objects.select_for_update().get(pk=structure.pk)
    if not structure.items.exists():
        raise ValidationError("Add at least one fee item before activation.")
    FeeStructure.objects.filter(
        school=structure.school, school_class=structure.school_class, term=structure.term,
        status=FeeStructure.Status.ACTIVE,
    ).exclude(pk=structure.pk).update(status=FeeStructure.Status.ARCHIVED)
    structure.status = FeeStructure.Status.ACTIVE
    structure.save(update_fields=["status"])
    return structure


@transaction.atomic
def post_structure_charges(*, structure, actor):
    _require_admin(actor, structure.school)
    structure = FeeStructure.objects.select_for_update().get(pk=structure.pk)
    if structure.status != FeeStructure.Status.ACTIVE:
        raise ValidationError("Only an active fee structure can be posted.")
    enrollments = ClassEnrollment.objects.filter(
        school_class=structure.school_class, status=ClassEnrollment.Status.ACTIVE,
        student__status=SchoolMembership.Status.ACTIVE,
    ).select_related("student")
    charges = []
    for enrollment in enrollments:
        for item in structure.items.all():
            charge, _ = Charge.objects.get_or_create(
                school=structure.school, student=enrollment.student, fee_item=item,
                defaults={"amount": item.amount, "posted_by": actor},
            )
            charges.append(charge)
    return charges


def ledger_summary(student):
    charges = student.charges.select_related("fee_item").all()
    adjustments = student.adjustments.all()
    payments = student.payments.all()
    charge_total = charges.aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
    debit_total = adjustments.filter(kind=Adjustment.Kind.DEBIT).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
    credit_total = adjustments.filter(kind=Adjustment.Kind.CREDIT).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
    paid_total = payments.filter(status=Payment.Status.SUCCESSFUL).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
    balance = charge_total + debit_total - credit_total - paid_total
    return {
        "charges": charges, "adjustments": adjustments, "payments": payments,
        "charge_total": charge_total, "debit_total": debit_total,
        "credit_total": credit_total, "paid_total": paid_total, "balance": balance,
    }


def can_pay_for(actor, student):
    if actor.school_id != student.school_id or not actor.is_active:
        return False
    if actor.role == SchoolMembership.Role.SCHOOL_ADMIN:
        return True
    return actor.role == SchoolMembership.Role.PARENT and GuardianLink.objects.filter(
        school=student.school, guardian=actor, student=student, status=GuardianLink.Status.ACTIVE
    ).exists()


@transaction.atomic
def initiate_mobile_money(*, student, actor, amount, email, phone, callback_url, gateway=None):
    if not can_pay_for(actor, student):
        raise PermissionDenied("You are not authorized to pay for this student.")
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValidationError("Payment amount must be greater than zero.")
    reference = f"NY-{student.school_id}-{secrets.token_hex(10)}"
    payment = Payment(
        school=student.school, student=student, initiated_by=actor, amount=amount,
        currency="GHS", channel=Payment.Channel.MOBILE_MONEY, status=Payment.Status.PENDING,
        provider="PAYSTACK", reference=reference, payer_email=email, payer_phone=phone,
    )
    payment.full_clean()
    payment.save()
    try:
        result = (gateway or PaystackGateway()).initialize(
            reference=reference, amount=amount, email=email, callback_url=callback_url
        )
    except Exception:
        payment.status = Payment.Status.UNKNOWN
        payment.save(update_fields=["status", "updated_at"])
        raise
    payment.authorization_url = result["authorization_url"]
    payment.provider_transaction_id = str(result.get("access_code", ""))
    payment.save(update_fields=["authorization_url", "provider_transaction_id", "updated_at"])
    return payment


def _allocate_payment(payment):
    remaining = payment.amount
    charges = Charge.objects.filter(student=payment.student).order_by("fee_item__due_date", "posted_at")
    for charge in charges:
        allocated = charge.allocations.filter(payment__status=Payment.Status.SUCCESSFUL).aggregate(
            total=models.Sum("amount")
        )["total"] or Decimal("0")
        outstanding = charge.amount - allocated
        amount = min(remaining, max(outstanding, Decimal("0")))
        if amount > 0:
            PaymentAllocation.objects.get_or_create(payment=payment, charge=charge, defaults={"amount": amount})
            remaining -= amount
        if remaining <= 0:
            break


def _issue_receipt(payment):
    number = f"NY-{payment.school_id}-{payment.pk:08d}"
    receipt, _ = Receipt.objects.get_or_create(
        school=payment.school, payment=payment,
        defaults={
            "number": number,
            "snapshot": {
                "number": number, "school": payment.school.name,
                "student": payment.student.user.get_full_name() or payment.student.user.username,
                "student_identifier": payment.student.identifier, "amount": str(payment.amount),
                "currency": payment.currency, "reference": payment.reference,
                "channel": payment.get_channel_display(), "paid_at": payment.successful_at.isoformat(),
            },
        },
    )
    return receipt


def _queue_receipt_notices(payment, receipt):
    templates = ensure_default_templates(payment.school)
    template = templates.get("receipt-email")
    if not template:
        return
    links = GuardianLink.objects.filter(
        school=payment.school, student=payment.student, status=GuardianLink.Status.ACTIVE
    ).select_related("guardian__user")
    context = {
        "school_name": payment.school.name,
        "student_name": payment.student.user.get_full_name() or payment.student.user.username,
        "receipt_number": receipt.number,
    }
    for link in links:
        enqueue_message(
            template=template, recipient=link.guardian, student=payment.student,
            business_reference=f"receipt:{receipt.pk}", context=context,
        )


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
    existing = ProviderEvent.objects.filter(provider="PAYSTACK", event_id=event_id).first()
    if existing:
        return existing
    reference = str(data.get("reference", ""))
    payment = Payment.objects.select_for_update().filter(provider="PAYSTACK", reference=reference).first()
    event = ProviderEvent.objects.create(
        provider="PAYSTACK", event_id=event_id, payment=payment, event_type=event_type,
        payload_digest=digest, signature_valid=True,
    )
    if not payment:
        return event
    provider_amount = Decimal(str(data.get("amount", 0))) / 100
    currency = data.get("currency", "")
    if provider_amount != payment.amount or currency != payment.currency:
        ReconciliationException.objects.create(
            school=payment.school, payment=payment, provider_event=event,
            reason="Provider amount or currency does not match the initiated payment.",
        )
        return event
    if event_type == "charge.success":
        if payment.status == Payment.Status.REVERSED:
            ReconciliationException.objects.create(
                school=payment.school, payment=payment, provider_event=event,
                reason="Success arrived after payment reversal.",
            )
            return event
        payment.status = Payment.Status.SUCCESSFUL
        payment.successful_at = timezone.now()
        payment.provider_transaction_id = str(data.get("id", ""))
        payment.save(update_fields=["status", "successful_at", "provider_transaction_id", "updated_at"])
        _allocate_payment(payment)
        receipt = _issue_receipt(payment)
        _queue_receipt_notices(payment, receipt)
        event.processed = True
        event.save(update_fields=["processed"])
    elif event_type in {"charge.failed", "transaction.failed"}:
        if payment.status == Payment.Status.PENDING:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
        event.processed = True
        event.save(update_fields=["processed"])
    elif event_type in {"charge.reversed", "refund.processed"}:
        if payment.status == Payment.Status.SUCCESSFUL:
            payment.status = Payment.Status.REVERSED
            payment.reversed_at = timezone.now()
            payment.save(update_fields=["status", "reversed_at", "updated_at"])
            event.processed = True
            event.save(update_fields=["processed"])
        else:
            ReconciliationException.objects.create(
                school=payment.school, payment=payment, provider_event=event,
                reason="Reversal received for a payment that is not successful.",
            )
    return event


@transaction.atomic
def record_adjustment(*, student, actor, kind, amount, reason):
    _require_admin(actor, student.school)
    reason = reason.strip()
    if not reason:
        raise ValidationError("An adjustment reason is required.")
    adjustment = Adjustment(
        school=student.school, student=student, kind=kind,
        amount=Decimal(amount), reason=reason, created_by=actor,
    )
    adjustment.full_clean()
    adjustment.save()
    return adjustment


@transaction.atomic
def resolve_exception(*, exception, actor, note):
    _require_admin(actor, exception.school)
    exception = ReconciliationException.objects.select_for_update().get(pk=exception.pk)
    if exception.status == ReconciliationException.Status.RESOLVED:
        raise ValidationError("This reconciliation exception is already resolved.")
    note = note.strip()
    if not note:
        raise ValidationError("A resolution note is required.")
    exception.status = ReconciliationException.Status.RESOLVED
    exception.resolved_by = actor
    exception.resolution_note = note
    exception.resolved_at = timezone.now()
    exception.save(update_fields=["status", "resolved_by", "resolution_note", "resolved_at"])
    return exception
