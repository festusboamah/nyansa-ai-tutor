import hashlib
import hmac
import json
from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from academics.models import AcademicYear, ClassEnrollment, SchoolClass, Term
from accounts.models import User
from guardians.models import GuardianLink
from schools.models import School, SchoolMembership

from .models import Adjustment, Charge, FeeItem, FeeStructure, Payment, PaymentAllocation, Receipt, ReconciliationException
from .services import (
    activate_fee_structure, initiate_mobile_money, ledger_summary, post_structure_charges,
    process_paystack_webhook, record_adjustment,
)


class FakePaystack:
    def initialize(self, **kwargs):
        return {"authorization_url": "https://checkout.paystack.test/abc", "access_code": "abc"}


@override_settings(PAYSTACK_SECRET_KEY="sk_test_phase7")
class FinanceWorkflowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Ledger School", slug="ledger-school")
        self.admin = self._member("ledger-admin", SchoolMembership.Role.SCHOOL_ADMIN)
        self.guardian = self._member("ledger-parent", SchoolMembership.Role.PARENT, "parent@example.com")
        self.student = self._member("ledger-student", SchoolMembership.Role.STUDENT)
        self.other_student = self._member("other-ledger-student", SchoolMembership.Role.STUDENT)
        GuardianLink.objects.create(
            school=self.school, guardian=self.guardian, student=self.student,
            relationship=GuardianLink.Relationship.FATHER,
            authorization_reference="FIN-CONSENT-1", authorized_by=self.admin,
        )
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027", start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31), is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", order=1,
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15),
        )
        self.school_class = SchoolClass.objects.create(
            school=self.school, academic_year=self.year, name="Basic 5"
        )
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.student)
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.other_student)
        self.structure = FeeStructure.objects.create(
            school=self.school, term=self.term, school_class=self.school_class,
            name="Term fees", created_by=self.admin,
        )
        self.item = FeeItem.objects.create(
            structure=self.structure, code="tuition", name="Tuition",
            amount=Decimal("500.00"), due_date=date(2026, 9, 30),
        )
        activate_fee_structure(structure=self.structure, actor=self.admin)
        post_structure_charges(structure=self.structure, actor=self.admin)

    def _member(self, username, role, email=""):
        user = User.objects.create_user(username=username, email=email, password="test-password")
        return SchoolMembership.objects.create(school=self.school, user=user, role=role)

    def _payment(self, amount="200.00"):
        return Payment.objects.create(
            school=self.school, student=self.student, initiated_by=self.guardian,
            amount=Decimal(amount), currency="GHS", channel=Payment.Channel.MOBILE_MONEY,
            reference=f"NY-TEST-{Payment.objects.count() + 1}", payer_email="parent@example.com",
        )

    def _event(self, payment, event="charge.success", amount=None, event_id=101):
        payload = json.dumps({
            "event": event,
            "data": {
                "id": event_id, "reference": payment.reference,
                "amount": int(Decimal(amount or payment.amount) * 100), "currency": "GHS",
            },
        }, separators=(",", ":")).encode()
        signature = hmac.new(b"sk_test_phase7", payload, hashlib.sha512).hexdigest()
        return payload, signature

    def test_structure_posting_is_idempotent_for_class_roster(self):
        first = post_structure_charges(structure=self.structure, actor=self.admin)
        second = post_structure_charges(structure=self.structure, actor=self.admin)
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)
        self.assertEqual(Charge.objects.count(), 2)

    def test_ledger_reconciles_charges_and_attributable_adjustments(self):
        record_adjustment(
            student=self.student, actor=self.admin, kind=Adjustment.Kind.CREDIT,
            amount="25.00", reason="Approved bursary",
        )
        summary = ledger_summary(self.student)
        self.assertEqual(summary["charge_total"], Decimal("500.00"))
        self.assertEqual(summary["balance"], Decimal("475.00"))
        adjustment = self.student.adjustments.get()
        adjustment.reason = "changed"
        with self.assertRaisesMessage(ValidationError, "immutable"):
            adjustment.save()

    def test_guardian_initializes_mobile_money_on_server(self):
        payment = initiate_mobile_money(
            student=self.student, actor=self.guardian, amount="120.00",
            email="parent@example.com", phone="0240000000",
            callback_url="https://nyansa.test/finance/payments/callback/", gateway=FakePaystack(),
        )
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.authorization_url, "https://checkout.paystack.test/abc")
        self.assertEqual(payment.channel, Payment.Channel.MOBILE_MONEY)

    def test_unlinked_guardian_cannot_pay(self):
        with self.assertRaises(PermissionDenied):
            initiate_mobile_money(
                student=self.other_student, actor=self.guardian, amount="10", email="parent@example.com",
                phone="0240000000", callback_url="https://nyansa.test/callback", gateway=FakePaystack(),
            )

    def test_invalid_webhook_signature_never_posts_payment(self):
        payment = self._payment()
        payload, _ = self._event(payment)
        with self.assertRaises(PermissionDenied):
            process_paystack_webhook(raw_body=payload, signature="invalid")
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertFalse(Receipt.objects.exists())

    def test_success_webhook_allocates_and_issues_stable_receipt(self):
        payment = self._payment()
        payload, signature = self._event(payment)
        event = process_paystack_webhook(raw_body=payload, signature=signature)
        payment.refresh_from_db()
        self.assertTrue(event.processed)
        self.assertEqual(payment.status, Payment.Status.SUCCESSFUL)
        self.assertEqual(PaymentAllocation.objects.get(payment=payment).amount, Decimal("200.00"))
        receipt = Receipt.objects.get(payment=payment)
        self.assertEqual(receipt.snapshot["amount"], "200.00")
        self.assertEqual(ledger_summary(self.student)["balance"], Decimal("300.00"))
        same = process_paystack_webhook(raw_body=payload, signature=signature)
        self.assertEqual(same.pk, event.pk)
        self.assertEqual(Receipt.objects.count(), 1)
        self.assertEqual(PaymentAllocation.objects.count(), 1)

    def test_amount_mismatch_enters_exception_queue_without_credit(self):
        payment = self._payment()
        payload, signature = self._event(payment, amount="199.00")
        process_paystack_webhook(raw_body=payload, signature=signature)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(ReconciliationException.objects.filter(payment=payment).count(), 1)
        self.assertFalse(Receipt.objects.exists())

    def test_failed_event_does_not_reduce_balance(self):
        payment = self._payment()
        payload, signature = self._event(payment, event="charge.failed")
        process_paystack_webhook(raw_body=payload, signature=signature)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertEqual(ledger_summary(self.student)["balance"], Decimal("500.00"))

    def test_reversal_restores_balance_without_deleting_history(self):
        payment = self._payment()
        payload, signature = self._event(payment, event_id=201)
        process_paystack_webhook(raw_body=payload, signature=signature)
        reverse_payload, reverse_signature = self._event(
            payment, event="charge.reversed", event_id=202
        )
        process_paystack_webhook(raw_body=reverse_payload, signature=reverse_signature)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REVERSED)
        self.assertEqual(ledger_summary(self.student)["balance"], Decimal("500.00"))
        self.assertEqual(payment.allocations.count(), 1)
        self.assertTrue(hasattr(payment, "receipt"))

    def test_browser_callback_cannot_mark_payment_successful(self):
        payment = self._payment()
        self.client.force_login(self.guardian.user)
        session = self.client.session
        session["active_school_id"] = self.school.pk
        session.save()
        response = self.client.get(
            reverse("payment_callback") + f"?reference={payment.reference}", secure=True
        )
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)
