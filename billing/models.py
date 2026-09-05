from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class LicensePlan(models.Model):
    class Code(models.TextChoices):
        STARTER = "STARTER", "Starter"
        STANDARD = "STANDARD", "Standard"
        PARTNER = "PARTNER", "Partner"
        INDIVIDUAL = "INDIVIDUAL", "Individual Teacher"

    class BillingPeriod(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"

    code = models.CharField(max_length=10, choices=Code.choices, unique=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    base_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    currency = models.CharField(max_length=3, default="GHS")
    billing_period = models.CharField(max_length=10, choices=BillingPeriod.choices, default=BillingPeriod.MONTHLY)
    ai_usage_markup_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class SchoolLicense(models.Model):
    class Status(models.TextChoices):
        TRIAL = "TRIAL", "Trial"
        ACTIVE = "ACTIVE", "Active"
        PAST_DUE = "PAST_DUE", "Past due"
        CANCELLED = "CANCELLED", "Cancelled"

    school = models.OneToOneField("schools.School", on_delete=models.CASCADE, related_name="license")
    plan = models.ForeignKey(LicensePlan, on_delete=models.PROTECT, related_name="school_licenses")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TRIAL)
    started_at = models.DateTimeField(auto_now_add=True)
    current_period_start = models.DateField()
    current_period_end = models.DateField()
    cancelled_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.school.name} - {self.plan.name} ({self.get_status_display()})"


class LicenseInvoice(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        VOID = "VOID", "Void"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="license_invoices")
    license = models.ForeignKey(SchoolLicense, on_delete=models.PROTECT, related_name="invoices")
    period_start = models.DateField()
    period_end = models.DateField()
    base_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    ai_usage_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    currency = models.CharField(max_length=3, default="GHS")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["license", "period_start", "period_end"], name="unique_license_invoice_period")
        ]

    def __str__(self):
        return f"{self.school.name} invoice {self.period_start} - {self.period_end}"


class LicensePayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESSFUL = "SUCCESSFUL", "Successful"
        FAILED = "FAILED", "Failed"
        UNKNOWN = "UNKNOWN", "Unknown"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="license_payments")
    invoice = models.ForeignKey(LicenseInvoice, on_delete=models.PROTECT, related_name="payments")
    initiated_by = models.ForeignKey("schools.SchoolMembership", on_delete=models.PROTECT, related_name="initiated_license_payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="GHS")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    provider = models.CharField(max_length=30, default="PAYSTACK")
    reference = models.CharField(max_length=80, unique=True)
    provider_transaction_id = models.CharField(max_length=120, blank=True)
    payer_email = models.EmailField()
    authorization_url = models.URLField(blank=True)
    successful_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def delete(self, *args, **kwargs):
        raise ValidationError("License payments cannot be deleted.")


class BillingProviderEvent(models.Model):
    provider = models.CharField(max_length=30)
    event_id = models.CharField(max_length=160)
    payment = models.ForeignKey(LicensePayment, null=True, blank=True, on_delete=models.PROTECT, related_name="provider_events")
    event_type = models.CharField(max_length=80)
    payload_digest = models.CharField(max_length=64)
    signature_valid = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "event_id"], name="unique_billing_provider_event")]
