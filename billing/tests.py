import hashlib
import hmac
import json
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from ai_core.models import AIUsageEvent
from schools.models import School, SchoolMembership

from .models import BillingProviderEvent, LicenseInvoice, LicensePayment, LicensePlan, SchoolLicense
from .services import generate_invoice, initiate_license_payment, process_paystack_webhook


class FakePaystack:
    def initialize(self, **kwargs):
        return {"authorization_url": "https://checkout.paystack.test/xyz", "access_code": "xyz"}


class FailingGateway:
    def initialize(self, **kwargs):
        raise RuntimeError("gateway is down")


@override_settings(PAYSTACK_SECRET_KEY="sk_test_billing")
class BillingWorkflowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Billing School", slug="billing-school")
        self.admin = self._member("billing-admin", SchoolMembership.Role.SCHOOL_ADMIN)
        # STARTER/STANDARD/PARTNER already exist from the 0002 seed migration.
        self.plan = LicensePlan.objects.get(code=LicensePlan.Code.STANDARD)
        self.starter_plan = LicensePlan.objects.get(code=LicensePlan.Code.STARTER)
        today = timezone.localdate()
        self.period_start = today - timedelta(days=31)
        self.period_end = today - timedelta(days=1)
        self.license = SchoolLicense.objects.create(
            school=self.school, plan=self.plan, status=SchoolLicense.Status.ACTIVE,
            current_period_start=self.period_start, current_period_end=self.period_end,
        )

    def _member(self, username, role, email=""):
        user = User.objects.create_user(username=username, email=email, password="test-password")
        return SchoolMembership.objects.create(school=self.school, user=user, role=role)

    def _event(self, payment, event="charge.success", amount=None, event_id=101):
        payload = json.dumps({
            "event": event,
            "data": {
                "id": event_id, "reference": payment.reference,
                "amount": int(Decimal(amount or payment.amount) * 100), "currency": "GHS",
            },
        }, separators=(",", ":")).encode()
        signature = hmac.new(b"sk_test_billing", payload, hashlib.sha512).hexdigest()
        return payload, signature

    def test_invoice_generation_includes_ai_usage_with_markup(self):
        # AIUsageEvent.created_at is auto_now_add, so it always gets the real
        # current timestamp - use a period that brackets "today" rather than
        # a fixed calendar date, so this doesn't depend on when the suite runs.
        today = timezone.localdate()
        period_start = today - timedelta(days=1)
        period_end = today + timedelta(days=1)
        AIUsageEvent.objects.create(
            school=self.school, source=AIUsageEvent.Source.STUDY_AI, model="claude-sonnet-4-5",
            input_tokens=1_000_000, output_tokens=1_000_000, succeeded=True,
        )
        invoice = generate_invoice(
            school_license=self.license, period_start=period_start, period_end=period_end,
        )
        self.assertEqual(invoice.base_amount, Decimal("1500.00"))
        self.assertIsNotNone(invoice.ai_usage_amount)
        self.assertGreater(invoice.ai_usage_amount, Decimal("0"))
        self.assertEqual(invoice.total_amount, invoice.base_amount + invoice.ai_usage_amount)

    def test_starter_plan_invoice_has_no_ai_usage_amount(self):
        starter_license = SchoolLicense.objects.create(
            school=School.objects.create(name="Starter School", slug="starter-school"),
            plan=self.starter_plan, status=SchoolLicense.Status.ACTIVE,
            current_period_start=date(2026, 8, 1), current_period_end=date(2026, 8, 31),
        )
        invoice = generate_invoice(
            school_license=starter_license, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
        )
        self.assertIsNone(invoice.ai_usage_amount)
        self.assertEqual(invoice.total_amount, Decimal("500.00"))

    def test_invoice_generation_is_idempotent(self):
        generate_invoice(school_license=self.license, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31))
        generate_invoice(school_license=self.license, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31))
        self.assertEqual(LicenseInvoice.objects.filter(license=self.license).count(), 1)

    def test_generate_license_invoices_command_advances_period_and_is_idempotent(self):
        call_command("generate_license_invoices")
        call_command("generate_license_invoices")

        self.assertEqual(LicenseInvoice.objects.count(), 1)
        self.license.refresh_from_db()
        self.assertEqual(self.license.current_period_start, self.period_end + timedelta(days=1))
        self.assertEqual(self.license.current_period_end, self.period_end + timedelta(days=31))

    def test_gateway_failure_leaves_payment_unknown_not_lost(self):
        invoice = generate_invoice(
            school_license=self.license, period_start=self.period_start, period_end=self.period_end,
        )
        with self.assertRaises(RuntimeError):
            initiate_license_payment(
                invoice=invoice, initiated_by=self.admin, email="admin@example.com",
                callback_url="https://nyansa.test/billing/payment/callback/", gateway=FailingGateway(),
            )
        payment = LicensePayment.objects.get(invoice=invoice)
        self.assertEqual(payment.status, LicensePayment.Status.UNKNOWN)

    def test_invalid_webhook_signature_never_marks_payment_paid(self):
        invoice = generate_invoice(
            school_license=self.license, period_start=self.period_start, period_end=self.period_end,
        )
        payment = initiate_license_payment(
            invoice=invoice, initiated_by=self.admin, email="admin@example.com",
            callback_url="https://nyansa.test/billing/payment/callback/", gateway=FakePaystack(),
        )
        payload, _ = self._event(payment)
        with self.assertRaises(PermissionDenied):
            process_paystack_webhook(raw_body=payload, signature="invalid")
        payment.refresh_from_db()
        self.assertEqual(payment.status, LicensePayment.Status.PENDING)

    def test_success_webhook_marks_payment_and_invoice_paid_and_activates_license(self):
        self.license.status = SchoolLicense.Status.TRIAL
        self.license.save(update_fields=["status"])
        invoice = generate_invoice(
            school_license=self.license, period_start=self.period_start, period_end=self.period_end,
        )
        payment = initiate_license_payment(
            invoice=invoice, initiated_by=self.admin, email="admin@example.com",
            callback_url="https://nyansa.test/billing/payment/callback/", gateway=FakePaystack(),
        )
        payload, signature = self._event(payment)

        process_paystack_webhook(raw_body=payload, signature=signature)

        payment.refresh_from_db()
        invoice.refresh_from_db()
        self.license.refresh_from_db()
        self.assertEqual(payment.status, LicensePayment.Status.SUCCESSFUL)
        self.assertEqual(invoice.status, LicenseInvoice.Status.PAID)
        self.assertEqual(self.license.status, SchoolLicense.Status.ACTIVE)

    def test_replayed_webhook_event_is_not_processed_twice(self):
        invoice = generate_invoice(
            school_license=self.license, period_start=self.period_start, period_end=self.period_end,
        )
        payment = initiate_license_payment(
            invoice=invoice, initiated_by=self.admin, email="admin@example.com",
            callback_url="https://nyansa.test/billing/payment/callback/", gateway=FakePaystack(),
        )
        payload, signature = self._event(payment)
        process_paystack_webhook(raw_body=payload, signature=signature)
        process_paystack_webhook(raw_body=payload, signature=signature)

        self.assertEqual(BillingProviderEvent.objects.filter(payment=payment).count(), 1)


class BillingViewTenancyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="View School", slug="view-school")
        self.other_school = School.objects.create(name="Other School", slug="other-billing-school")
        self.admin = User.objects.create_user(username="view-admin", password="test-password")
        SchoolMembership.objects.create(school=self.school, user=self.admin, role=SchoolMembership.Role.SCHOOL_ADMIN)
        self.teacher = User.objects.create_user(username="view-teacher", password="test-password", role=User.Role.TEACHER)
        SchoolMembership.objects.create(school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER)

        self.plan = LicensePlan.objects.get(code=LicensePlan.Code.STARTER)
        other_license = SchoolLicense.objects.create(
            school=self.other_school, plan=self.plan, status=SchoolLicense.Status.ACTIVE,
            current_period_start=date(2026, 8, 1), current_period_end=date(2026, 8, 31),
        )
        self.other_invoice = generate_invoice(
            school_license=other_license, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
        )

    def test_teacher_cannot_view_billing_dashboard(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("billing_dashboard"), secure=True)
        self.assertEqual(response.status_code, 403)

    def test_school_admin_cannot_pay_another_schools_invoice(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("billing_pay_invoice", args=[self.other_invoice.id]), secure=True)
        self.assertEqual(response.status_code, 404)

    def test_selecting_a_plan_creates_a_trial_license(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("billing_plans"), {"plan_id": self.plan.id}, secure=True)
        self.assertRedirects(response, reverse("billing_dashboard"), fetch_redirect_response=False)
        license = SchoolLicense.objects.get(school=self.school)
        self.assertEqual(license.status, SchoolLicense.Status.TRIAL)
        self.assertEqual(license.plan, self.plan)
