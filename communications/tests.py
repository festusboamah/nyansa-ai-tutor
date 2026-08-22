from unittest.mock import patch
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from django.core.files.uploadedfile import SimpleUploadedFile

from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, TeacherAssignment, Term
from accounts.models import User
from courses.models import Subject
from dashboard.lesson_workflow import record_initial_lesson_version, review_lesson_note, submit_lesson_note
from dashboard.models import LessonNote
from gradebook.history import record_grade_entry, review_grade_entry
from gradebook.models import Assessment, AssessmentCategory, GradeEntry, GradeReviewDecision, GradeScheme
from guardians.models import GuardianLink
from quizzes.models import Assignment, AssignmentSubmission
from schools.models import School, SchoolMembership

from .models import CommunicationPreference, DeliveryAttempt, MessageIntent, MessageTemplate, Notification
from .services import archive_stale_notifications, create_notification, enqueue_guardian_event, enqueue_message, ensure_default_templates, process_queued_messages


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

    def test_inbox_filters_by_category_and_unread_status(self):
        lesson = create_notification(
            recipient=self.teacher, kind=Notification.Kind.LESSON_REVIEW,
            title="Lesson alert", message="Review update", target_url="/dashboard/",
            deduplication_key="filter:lesson",
        )
        assignment = create_notification(
            recipient=self.teacher, kind=Notification.Kind.ASSIGNMENT,
            title="Assignment alert", message="New work", target_url="/dashboard/",
            deduplication_key="filter:assignment",
        )
        assignment.read_at = timezone.now()
        assignment.save(update_fields=["read_at"])
        response = self.client.get(
            reverse("notification_center"),
            {"kind": Notification.Kind.LESSON_REVIEW, "unread": "1"}, secure=True,
        )
        self.assertContains(response, lesson.title)
        self.assertNotContains(response, assignment.title)

    def test_old_read_notifications_are_archived_not_deleted(self):
        notification = create_notification(
            recipient=self.teacher, kind=Notification.Kind.GRADE_REVIEW,
            title="Old alert", message="Historical update", target_url="/gradebook/",
            deduplication_key="old:grade",
        )
        old_time = timezone.now() - timedelta(days=100)
        Notification.objects.filter(pk=notification.pk).update(created_at=old_time, read_at=old_time)
        archive_stale_notifications(recipient=self.teacher)
        notification.refresh_from_db()
        self.assertIsNotNone(notification.archived_at)
        self.assertTrue(Notification.objects.filter(pk=notification.pk).exists())


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


class GradebookDomainEventReceiverTests(TestCase):
    """communications listens to gradebook.signals events rather than gradebook
    importing communications - these tests verify that boundary still produces
    the same notifications the old direct calls did."""

    def setUp(self):
        self.school = School.objects.create(name="Signal School", slug="signal-school")
        self.admin = self._member("signal-admin", SchoolMembership.Role.SCHOOL_ADMIN)
        self.teacher = self._member("signal-teacher", SchoolMembership.Role.TEACHER)
        self.student = self._member("signal-student", SchoolMembership.Role.STUDENT)
        year = AcademicYear.objects.create(
            school=self.school, name="2026/2027", start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31), is_current=True,
        )
        term = Term.objects.create(
            academic_year=year, name="Term 1", order=1,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
        )
        school_class = SchoolClass.objects.create(school=self.school, academic_year=year, name="Basic 6")
        ClassEnrollment.objects.create(school_class=school_class, student=self.student)
        subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.offering = SubjectOffering.objects.create(
            school=self.school, school_class=school_class, subject=subject, term=term
        )
        scheme = GradeScheme.objects.create(
            school=self.school, academic_year=year, name="Standard", status=GradeScheme.Status.ACTIVE
        )
        category = AssessmentCategory.objects.create(
            scheme=scheme, name="Coursework", code="coursework", weight=Decimal("100"), order=1
        )
        self.assessment = Assessment.objects.create(
            school=self.school, offering=self.offering, category=category,
            title="Test one", max_score=Decimal("100"), status=Assessment.Status.PUBLISHED,
        )

    def _member(self, username, role):
        user = User.objects.create_user(username=username, password="test-password")
        return SchoolMembership.objects.create(school=self.school, user=user, role=role)

    def test_publishing_a_grade_entry_notifies_admins(self):
        entry, _ = record_grade_entry(
            school=self.school, assessment=self.assessment, student=self.student, actor=self.teacher,
            score=Decimal("70"), source=GradeEntry.Source.MANUAL, status=GradeEntry.Status.PUBLISHED,
            reason="Initial entry",
        )
        notification = Notification.objects.get(recipient=self.admin, kind=Notification.Kind.GRADE_REVIEW)
        self.assertEqual(notification.title, "Grade awaiting approval")
        self.assertIn("signal-teacher", notification.message)

    def test_review_decision_notifies_the_recording_teacher(self):
        entry, _ = record_grade_entry(
            school=self.school, assessment=self.assessment, student=self.student, actor=self.teacher,
            score=Decimal("70"), source=GradeEntry.Source.MANUAL, status=GradeEntry.Status.PUBLISHED,
            reason="Initial entry",
        )
        Notification.objects.filter(recipient=self.admin).delete()

        review_grade_entry(
            entry=entry, reviewer=self.admin, decision=GradeReviewDecision.Decision.APPROVED,
        )

        notification = Notification.objects.get(recipient=self.teacher, kind=Notification.Kind.GRADE_REVIEW)
        self.assertEqual(notification.title, "Grade review completed")


class AssignmentSubmissionReceiverTests(TestCase):
    """communications listens to AssignmentSubmission's own post_save signal
    rather than quizzes importing communications directly."""

    def setUp(self):
        self.school = School.objects.create(name="Assignment Signal School", slug="assignment-signal-school")
        self.teacher_user = User.objects.create_user(
            username="assignment-signal-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.teacher = SchoolMembership.objects.create(
            school=self.school, user=self.teacher_user, role=SchoolMembership.Role.TEACHER
        )
        self.student_user = User.objects.create_user(username="assignment-signal-student", password="test-password")
        SchoolMembership.objects.create(
            school=self.school, user=self.student_user, role=SchoolMembership.Role.STUDENT
        )
        subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.assignment = Assignment.objects.create(subject=subject, teacher=self.teacher_user, title="Essay")

    def _submit(self):
        return AssignmentSubmission.objects.create(
            assignment=self.assignment, student=self.student_user,
            file=SimpleUploadedFile("essay.pdf", b"content", content_type="application/pdf"),
        )

    def test_submitting_an_assignment_notifies_the_teacher(self):
        submission = self._submit()

        notification = Notification.objects.get(recipient=self.teacher, kind=Notification.Kind.ASSIGNMENT)
        self.assertEqual(notification.title, "New assignment submission")
        self.assertIn("assignment-signal-student", notification.message)
        self.assertEqual(notification.deduplication_key, f"assignment-submission:{submission.id}")

    def test_resaving_a_submission_does_not_notify_again(self):
        submission = self._submit()
        submission.final_score = 80
        submission.save()

        self.assertEqual(Notification.objects.filter(recipient=self.teacher).count(), 1)


class LessonNoteDomainEventReceiverTests(TestCase):
    """communications listens to dashboard.signals events rather than
    dashboard importing communications directly."""

    def setUp(self):
        self.school = School.objects.create(name="Lesson Signal School", slug="lesson-signal-school")
        self.teacher_user = User.objects.create_user(
            username="lesson-signal-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.teacher = SchoolMembership.objects.create(
            school=self.school, user=self.teacher_user, role=SchoolMembership.Role.TEACHER
        )
        self.admin_user = User.objects.create_user(username="lesson-signal-admin", password="test-password")
        self.admin = SchoolMembership.objects.create(
            school=self.school, user=self.admin_user, role=SchoolMembership.Role.SCHOOL_ADMIN
        )
        subject = Subject.objects.create(school=self.school, name="Science")
        self.note = LessonNote.objects.create(
            teacher=self.teacher_user, subject=subject, class_level="JHS 1",
            week_ending=date(2026, 8, 7), strand_topic="Living things",
            learning_indicator="Classify living things.",
        )
        record_initial_lesson_version(note=self.note, actor=self.teacher)

    def test_submitting_a_lesson_note_notifies_admins(self):
        submit_lesson_note(note=self.note, actor=self.teacher, message="Ready for review")

        notification = Notification.objects.get(recipient=self.admin, kind=Notification.Kind.LESSON_REVIEW)
        self.assertEqual(notification.title, "Lesson note awaiting review")
        self.assertIn("Living things", notification.message)

    def test_approving_a_lesson_note_notifies_the_author(self):
        submit_lesson_note(note=self.note, actor=self.teacher, message="Ready for review")
        Notification.objects.filter(recipient=self.admin).delete()

        review_lesson_note(note=self.note, actor=self.admin, action="approve")

        notification = Notification.objects.get(recipient=self.teacher, kind=Notification.Kind.LESSON_REVIEW)
        self.assertEqual(notification.title, "Lesson note review update")
        self.assertIn("approved", notification.message)
        self.assertIn("approved", notification.message.lower())


class StaffAssignmentReceiverTests(TestCase):
    """communications listens to TeacherAssignment/SchoolClass post_save/post_delete
    signals rather than academics importing communications directly."""

    def setUp(self):
        self.school = School.objects.create(name="Staff Signal School", slug="staff-signal-school")
        self.teacher = self._member("staff-signal-teacher")
        self.other_teacher = self._member("staff-signal-other-teacher")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027", start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31), is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", order=1,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
        )
        self.school_class = SchoolClass.objects.create(
            school=self.school, academic_year=self.year, name="Basic 6"
        )
        subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.offering = SubjectOffering.objects.create(
            school=self.school, school_class=self.school_class, subject=subject, term=self.term
        )

    def _member(self, username):
        user = User.objects.create_user(username=username, password="test-password")
        return SchoolMembership.objects.create(school=self.school, user=user, role=SchoolMembership.Role.TEACHER)

    def test_creating_a_teacher_assignment_notifies_the_teacher(self):
        assignment = TeacherAssignment.objects.create(offering=self.offering, teacher=self.teacher, is_lead=True)

        notification = Notification.objects.get(recipient=self.teacher, kind=Notification.Kind.STAFF_ASSIGNMENT)
        self.assertEqual(notification.title, "New subject assignment")
        self.assertIn("Mathematics", notification.message)
        self.assertIn("lead teacher", notification.message)
        self.assertEqual(notification.deduplication_key, f"teacher-assignment:{assignment.id}:created")

    def test_deleting_a_teacher_assignment_notifies_the_teacher(self):
        assignment = TeacherAssignment.objects.create(offering=self.offering, teacher=self.teacher)
        Notification.objects.filter(recipient=self.teacher).delete()

        assignment.delete()

        notification = Notification.objects.get(recipient=self.teacher, kind=Notification.Kind.STAFF_ASSIGNMENT)
        self.assertEqual(notification.title, "Subject assignment removed")
        self.assertIn("Mathematics", notification.message)

    def test_assigning_a_class_teacher_notifies_the_new_teacher(self):
        self.school_class.class_teacher = self.teacher
        self.school_class.save()

        notification = Notification.objects.get(recipient=self.teacher, kind=Notification.Kind.STAFF_ASSIGNMENT)
        self.assertEqual(notification.title, "New class-teacher assignment")

    def test_reassigning_class_teacher_notifies_previous_and_new_teacher(self):
        self.school_class.class_teacher = self.teacher
        self.school_class.save()
        Notification.objects.all().delete()

        self.school_class.class_teacher = self.other_teacher
        self.school_class.save()

        new_notification = Notification.objects.get(
            recipient=self.other_teacher, kind=Notification.Kind.STAFF_ASSIGNMENT
        )
        self.assertEqual(new_notification.title, "New class-teacher assignment")
        previous_notification = Notification.objects.get(
            recipient=self.teacher, kind=Notification.Kind.STAFF_ASSIGNMENT
        )
        self.assertEqual(previous_notification.title, "Class-teacher assignment changed")

    def test_resaving_school_class_without_changing_teacher_does_not_notify_again(self):
        self.school_class.class_teacher = self.teacher
        self.school_class.save()
        self.assertEqual(Notification.objects.filter(recipient=self.teacher).count(), 1)

        self.school_class.capacity = 40
        self.school_class.save()

        self.assertEqual(Notification.objects.filter(recipient=self.teacher).count(), 1)
