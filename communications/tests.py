from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from guardians.models import GuardianLink
from schools.models import School, SchoolMembership

from .models import CommunicationPreference, DeliveryAttempt, MessageIntent, MessageTemplate, Notification
from .services import create_notification, enqueue_guardian_event, enqueue_message, ensure_default_templates, process_queued_messages


class NotificationCenterTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Inbox School", slug="inbox-school")
        user = User.objects.create_user(username="inbox-teacher", password="test-password")
        self.teacher = SchoolMembership.objects.create(
            school=self.school, user=user, role=SchoolMembership.Role.TEACHER
        )
        self.client.force_login(user)

    def test_inbox_marks_owned_notification_read_and_redirects(self):
        notification = create_notification(
            recipient=self.teacher,
            kind=Notification.Kind.ASSIGNMENT,
            title="New submission",
            message="A learner submitted an assignment.",
            target_url="/dashboard/",
            deduplication_key="submission:1",
        )
        response = self.client.get(reverse("notification_center"), secure=True)
        self.assertContains(response, "New submission")
        response = self.client.get(reverse("notification_read", args=[notification.id]), secure=True)
        self.assertRedirects(response, "/dashboard/", fetch_redirect_response=False)
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)

    def test_notification_cannot_be_read_by_another_school(self):
        notification = create_notification(
            recipient=self.teacher,
            kind=Notification.Kind.LESSON_REVIEW,
            title="Private alert",
            message="School-scoped content",
            target_url="/dashboard/",
            deduplication_key="private:1",
        )
        other_school = School.objects.create(name="Other School", slug="other-school")
        other_user = User.objects.create_user(username="other-admin", password="test-password")
        SchoolMembership.objects.create(
            school=other_school, user=other_user, role=SchoolMembership.Role.SCHOOL_ADMIN
        )
        self.client.force_login(other_user)
        response = self.client.get(reverse("notification_read", args=[notification.id]), secure=True)
        self.assertEqual(response.status_code, 404)

    def test_students_cannot_open_staff_notification_center(self):
        student_user = User.objects.create_user(username="inbox-student", password="test-password")
        SchoolMembership.objects.create(
            school=self.school, user=student_user, role=SchoolMembership.Role.STUDENT
        )
        self.client.force_login(student_user)
        response = self.client.get(reverse("notification_center"), secure=True)
        self.assertEqual(response.status_code, 403)


class FakeGateway:
    name = "fake"

    def __init__(self, error=None):
        self.error = error

    def send(self, **kwargs):
        if self.error:
            raise RuntimeError(self.error)
        return "provider-123"


class CommunicationWorkflowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Message School", slug="message-school")
        self.admin = self._member("message-admin", SchoolMembership.Role.SCHOOL_ADMIN)
        self.guardian = self._member("message-parent", SchoolMembership.Role.PARENT, "parent@example.com")
        self.student = self._member("message-student", SchoolMembership.Role.STUDENT)
        GuardianLink.objects.create(
            school=self.school, guardian=self.guardian, student=self.student,
            relationship=GuardianLink.Relationship.MOTHER,
            authorization_reference="CONSENT-EMAIL-1", authorized_by=self.admin,
        )
        self.templates = ensure_default_templates(self.school)

    def _member(self, username, role, email=""):
        user = User.objects.create_user(username=username, email=email, password="test-password")
        return SchoolMembership.objects.create(school=self.school, user=user, role=role)

    def test_enqueue_is_idempotent_for_one_business_event(self):
        template = self.templates["report-email"]
        kwargs = {
            "template": template, "recipient": self.guardian, "student": self.student,
            "business_reference": "report:42:v1",
            "context": {"school_name": self.school.name, "student_name": "Ama"},
        }
        first = enqueue_message(**kwargs)
        second = enqueue_message(**kwargs)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(MessageIntent.objects.count(), 1)

    def test_preferences_opt_out_without_losing_portal_access(self):
        CommunicationPreference.objects.create(recipient=self.guardian, email_enabled=False)
        intent = enqueue_message(
            template=self.templates["report-email"], recipient=self.guardian, student=self.student,
            business_reference="report:43:v1",
            context={"school_name": self.school.name, "student_name": "Ama"},
        )
        self.assertIsNone(intent)
        self.assertEqual(MessageIntent.objects.count(), 0)

    def test_sms_template_rejects_sensitive_content_flag(self):
        template = MessageTemplate(
            school=self.school, code="unsafe-sms", name="Unsafe", channel=MessageTemplate.Channel.SMS,
            event_type=MessageTemplate.EventType.BALANCE, body_template="Balance update",
            contains_sensitive_data=True,
        )
        with self.assertRaisesMessage(ValidationError, "sensitive"):
            template.full_clean()

    @patch("communications.services.gateway_for", return_value=FakeGateway())
    def test_worker_records_success_and_does_not_resend(self, gateway):
        intent = enqueue_message(
            template=self.templates["report-email"], recipient=self.guardian, student=self.student,
            business_reference="report:44:v1",
            context={"school_name": self.school.name, "student_name": "Ama"},
        )
        process_queued_messages(now=timezone.now())
        intent.refresh_from_db()
        self.assertEqual(intent.status, MessageIntent.Status.SENT)
        self.assertEqual(intent.attempt_count, 1)
        self.assertEqual(intent.delivery_attempts.filter(succeeded=True).count(), 1)
        process_queued_messages(now=timezone.now())
        self.assertEqual(DeliveryAttempt.objects.count(), 1)

    @patch("communications.services.gateway_for", return_value=FakeGateway("temporary outage"))
    def test_failed_delivery_is_scheduled_for_retry(self, gateway):
        intent = enqueue_message(
            template=self.templates["report-email"], recipient=self.guardian, student=self.student,
            business_reference="report:45:v1",
            context={"school_name": self.school.name, "student_name": "Ama"},
        )
        process_queued_messages(now=timezone.now())
        intent.refresh_from_db()
        self.assertEqual(intent.status, MessageIntent.Status.FAILED)
        self.assertEqual(intent.attempt_count, 1)
        self.assertIn("temporary outage", intent.last_error)
        self.assertIsNotNone(intent.next_attempt_at)

    def test_guardian_event_queues_only_authorized_recipient_channels(self):
        intents = enqueue_guardian_event(
            student=self.student, event_type=MessageTemplate.EventType.REPORT,
            business_reference="report:46:v1", context={},
        )
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].recipient, self.guardian)
        self.assertNotIn("72", intents[0].rendered_body)

    def test_delivery_attempt_is_immutable(self):
        intent = enqueue_message(
            template=self.templates["report-email"], recipient=self.guardian, student=self.student,
            business_reference="report:47:v1",
            context={"school_name": self.school.name, "student_name": "Ama"},
        )
        attempt = DeliveryAttempt.objects.create(
            intent=intent, attempt_number=1, succeeded=False, provider="fake", error="offline"
        )
        attempt.error = "changed"
        with self.assertRaisesMessage(ValidationError, "immutable"):
            attempt.save()
