from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class FeeStructure(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="fee_structures")
    term = models.ForeignKey("academics.Term", on_delete=models.PROTECT, related_name="fee_structures")
    school_class = models.ForeignKey("academics.SchoolClass", on_delete=models.PROTECT, related_name="fee_structures")
    name = models.CharField(max_length=120)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey("schools.SchoolMembership", on_delete=models.PROTECT, related_name="created_fee_structures")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school_class", "term", "name", "version"], name="unique_fee_structure_version")]

    def clean(self):
        if self.term_id and self.term.academic_year.school_id != self.school_id:
            raise ValidationError("Fee structure term must belong to its school.")
        if self.school_class_id and self.school_class.school_id != self.school_id:
            raise ValidationError("Fee structure class must belong to its school.")
        if self.term_id and self.school_class_id and self.term.academic_year_id != self.school_class.academic_year_id:
            raise ValidationError("Fee structure class and term must share an academic year.")


class FeeItem(models.Model):
    structure = models.ForeignKey(FeeStructure, on_delete=models.PROTECT, related_name="items")
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    due_date = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["structure", "code"], name="unique_fee_item_code")]


class Charge(models.Model):
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="charges")
    student = models.ForeignKey("schools.SchoolMembership", on_delete=models.PROTECT, related_name="charges")
    fee_item = models.ForeignKey(FeeItem, on_delete=models.PROTECT, related_name="charges")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    posted_by = models.ForeignKey("schools.SchoolMembership", on_delete=models.PROTECT, related_name="posted_charges")
    posted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "fee_item"], name="unique_student_fee_charge")]

    def clean(self):
        if self.student_id and (self.student.school_id != self.school_id or self.student.role != "STUDENT"):
            raise ValidationError("Charge student must belong to its school.")
        if self.fee_item_id and self.fee_item.structure.school_id != self.school_id:
            raise ValidationError("Charge item must belong to its school.")

    def delete(self, *args, **kwargs):
        raise ValidationError("Posted charges cannot be deleted; use an adjustment.")


class Adjustment(models.Model):
    class Kind(models.TextChoices):
        DEBIT = "DEBIT", "Debit"
        CREDIT = "CREDIT", "Credit"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="adjustments")
    student = models.ForeignKey("schools.SchoolMembership", on_delete=models.PROTECT, related_name="adjustments")
    kind = models.CharField(max_length=6, choices=Kind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    reason = models.CharField(max_length=500)
    created_by = models.ForeignKey("schools.SchoolMembership", on_delete=models.PROTECT, related_name="created_adjustments")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Adjustments are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Adjustments are immutable.")


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESSFUL = "SUCCESSFUL", "Successful"
        FAILED = "FAILED", "Failed"
        REVERSED = "REVERSED", "Reversed"
        UNKNOWN = "UNKNOWN", "Unknown"

    class Channel(models.TextChoices):
        MOBILE_MONEY = "MOBILE_MONEY", "Mobile Money"
        CASH = "CASH", "Cash"
        BANK = "BANK", "Bank transfer"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="payments")
    student = models.ForeignKey("schools.SchoolMembership", on_delete=models.PROTECT, related_name="payments")
    initiated_by = models.ForeignKey("schools.SchoolMembership", on_delete=models.PROTECT, related_name="initiated_payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="GHS")
    channel = models.CharField(max_length=20, choices=Channel.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    provider = models.CharField(max_length=30, default="PAYSTACK")
    reference = models.CharField(max_length=80, unique=True)
    provider_transaction_id = models.CharField(max_length=120, blank=True)
    payer_email = models.EmailField()
    payer_phone = models.CharField(max_length=30, blank=True)
    authorization_url = models.URLField(blank=True)
    successful_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.student_id and (self.student.school_id != self.school_id or self.student.role != "STUDENT"):
            raise ValidationError("Payment student must belong to its school.")
        if self.initiated_by_id and self.initiated_by.school_id != self.school_id:
            raise ValidationError("Payment initiator must belong to its school.")

    def delete(self, *args, **kwargs):
        raise ValidationError("Payments cannot be deleted.")


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="allocations")
    charge = models.ForeignKey(Charge, on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["payment", "charge"], name="unique_payment_charge_allocation")]

    def delete(self, *args, **kwargs):
        raise ValidationError("Payment allocations cannot be deleted.")


class Receipt(models.Model):
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="receipts")
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="receipt")
    number = models.CharField(max_length=40)
    snapshot = models.JSONField(default=dict)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "number"], name="unique_school_receipt_number")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Receipts are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Receipts are immutable.")


class ProviderEvent(models.Model):
    provider = models.CharField(max_length=30)
    event_id = models.CharField(max_length=160)
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.PROTECT, related_name="provider_events")
    event_type = models.CharField(max_length=80)
    payload_digest = models.CharField(max_length=64)
    signature_valid = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "event_id"], name="unique_provider_event")]


class ReconciliationException(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        RESOLVED = "RESOLVED", "Resolved"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="reconciliation_exceptions")
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.PROTECT, related_name="exceptions")
    provider_event = models.ForeignKey(ProviderEvent, on_delete=models.PROTECT, related_name="exceptions")
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    resolved_by = models.ForeignKey("schools.SchoolMembership", null=True, blank=True, on_delete=models.PROTECT, related_name="resolved_payment_exceptions")
    resolution_note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
