from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import PermissionDenied, ValidationError

from accounts.models import User
from courses.models import Subject
from schools.models import School, SchoolMembership

from .lesson_workflow import (
    add_lesson_comment,
    record_initial_lesson_version,
    revise_lesson_note,
    review_lesson_note,
    submit_lesson_note,
)
from .models import LessonNote, LessonNoteEvent, LessonNoteNotification, LessonNoteVersion


class LessonNoteAccessBaselineTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher", password="test-password", role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            username="other-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(username="student", password="test-password")
        self.school = School.objects.create(name="Lesson School", slug="lesson-school")
        SchoolMembership.objects.create(
            school=self.school, user=self.teacher, role=SchoolMembership.Role.TEACHER
        )
        SchoolMembership.objects.create(
            school=self.school,
            user=self.other_teacher,
            role=SchoolMembership.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            school=self.school, user=self.student, role=SchoolMembership.Role.STUDENT
        )
        self.subject = Subject.objects.create(school=self.school, name="Integrated Science")
        self.note = LessonNote.objects.create(
            teacher=self.teacher,
            subject=self.subject,
            class_level="JHS 2",
            week_ending=date(2026, 7, 31),
            strand_topic="Reproduction",
            learning_indicator="Describe the stages of reproduction.",
        )

    def test_student_cannot_open_teacher_dashboard(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("teacher_dashboard"), secure=True)

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_teacher_only_sees_own_lesson_note_list(self):
        self.client.force_login(self.other_teacher)

        response = self.client.get(reverse("lesson_notes_list"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.note.strand_topic)

    def test_teacher_cannot_open_another_teachers_lesson_note(self):
        self.client.force_login(self.other_teacher)

        response = self.client.get(
            reverse("lesson_note_detail", args=[self.note.id]), secure=True
        )

        self.assertEqual(response.status_code, 404)

    def test_teacher_can_open_teacher_dashboard(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("teacher_dashboard"), secure=True)

        self.assertEqual(response.status_code, 200)

    def test_student_has_no_lesson_updates_navigation_or_page_access(self):
        self.client.force_login(self.student)

        home = self.client.get(reverse("home"), secure=True)
        notifications = self.client.get(reverse("lesson_notifications"), secure=True)

        self.assertNotContains(home, "Lesson Updates")
        self.assertRedirects(notifications, reverse("home"), fetch_redirect_response=False)

    def test_teacher_has_lesson_updates_navigation_and_page_access(self):
        self.client.force_login(self.teacher)

        home = self.client.get(reverse("home"), secure=True)
        notifications = self.client.get(reverse("lesson_notifications"), secure=True)

        self.assertContains(home, "Lesson Updates")
        self.assertEqual(notifications.status_code, 200)


class LessonNoteApprovalWorkflowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Approval School", slug="approval-school")
        self.teacher_user = User.objects.create_user(
            username="lesson-author", password="test-password", role=User.Role.TEACHER
        )
        self.teacher = SchoolMembership.objects.create(
            school=self.school, user=self.teacher_user, role=SchoolMembership.Role.TEACHER
        )
        self.admin_user = User.objects.create_user(username="lesson-reviewer", password="test-password")
        self.administrator = SchoolMembership.objects.create(
            school=self.school, user=self.admin_user, role=SchoolMembership.Role.SCHOOL_ADMIN
        )
        self.subject = Subject.objects.create(school=self.school, name="Science")
        self.note = LessonNote.objects.create(
            teacher=self.teacher_user,
            subject=self.subject,
            class_level="JHS 1",
            week_ending=date(2026, 8, 7),
            strand_topic="Living things",
            learning_indicator="Classify living things.",
            generated_content='{"days": [{"day": "Monday", "starter": "Observe", "main": "Classify", "reflection": "Review"}]}',
        )

    def test_complete_return_revision_approval_and_reopen_lifecycle(self):
        version = record_initial_lesson_version(note=self.note, actor=self.teacher)
        self.assertEqual(version.version_number, 1)
        submit_lesson_note(note=self.note, actor=self.teacher, message="Ready for review")
        self.note.refresh_from_db()
        self.assertEqual(self.note.status, LessonNote.Status.PENDING_REVIEW)
        self.assertEqual(
            LessonNoteNotification.objects.filter(recipient=self.administrator).count(), 1
        )

        review_lesson_note(
            note=self.note,
            actor=self.administrator,
            action="return",
            message="Add a practical activity.",
        )
        revise_lesson_note(
            note=self.note,
            actor=self.teacher,
            values={"resources": "Leaves and picture cards"},
            reason="Added requested practical resources",
        )
        self.note.refresh_from_db()
        self.assertEqual(self.note.status, LessonNote.Status.DRAFT)
        self.assertEqual(self.note.current_version, 2)

        submit_lesson_note(note=self.note, actor=self.teacher)
        review_lesson_note(note=self.note, actor=self.administrator, action="approve")
        self.note.refresh_from_db()
        self.assertEqual(self.note.status, LessonNote.Status.APPROVED)
        self.note.resources = "Silently changed"
        with self.assertRaisesMessage(ValidationError, "locked"):
            self.note.save()

        self.note.refresh_from_db()
        review_lesson_note(
            note=self.note,
            actor=self.administrator,
            action="reopen",
            message="Curriculum reference changed.",
        )
        revise_lesson_note(
            note=self.note,
            actor=self.teacher,
            values={"reference": "Updated curriculum page 14"},
            reason="Updated curriculum reference",
        )
        self.note.refresh_from_db()
        self.assertEqual(self.note.current_version, 3)
        self.assertEqual(self.note.status, LessonNote.Status.DRAFT)
        self.assertEqual(self.note.versions.count(), 3)

    def test_return_and_reopen_require_comments(self):
        record_initial_lesson_version(note=self.note, actor=self.teacher)
        submit_lesson_note(note=self.note, actor=self.teacher)
        with self.assertRaisesMessage(ValidationError, "comment is required"):
            review_lesson_note(note=self.note, actor=self.administrator, action="return")
        review_lesson_note(note=self.note, actor=self.administrator, action="approve")
        with self.assertRaisesMessage(ValidationError, "reason is required"):
            review_lesson_note(note=self.note, actor=self.administrator, action="reopen")

    def test_non_author_cannot_revise_or_submit(self):
        other_user = User.objects.create_user(
            username="other-author", password="test-password", role=User.Role.TEACHER
        )
        other = SchoolMembership.objects.create(
            school=self.school, user=other_user, role=SchoolMembership.Role.TEACHER
        )
        with self.assertRaises(PermissionDenied):
            revise_lesson_note(
                note=self.note,
                actor=other,
                values={"resources": "Other"},
                reason="Unauthorized change",
            )
        with self.assertRaises(PermissionDenied):
            submit_lesson_note(note=self.note, actor=other)

    def test_other_school_administrator_cannot_review(self):
        other_school = School.objects.create(name="Other School", slug="lesson-other-school")
        other_admin_user = User.objects.create_user(username="other-admin", password="test-password")
        other_admin = SchoolMembership.objects.create(
            school=other_school, user=other_admin_user, role=SchoolMembership.Role.SCHOOL_ADMIN
        )
        record_initial_lesson_version(note=self.note, actor=self.teacher)
        submit_lesson_note(note=self.note, actor=self.teacher)
        with self.assertRaises(PermissionDenied):
            review_lesson_note(note=self.note, actor=other_admin, action="approve")

    def test_comments_are_immutable_and_notify_counterparty(self):
        event = add_lesson_comment(
            note=self.note, actor=self.administrator, message="Clarify the reflection prompt."
        )
        self.assertEqual(event.event_type, LessonNoteEvent.EventType.COMMENT)
        self.assertTrue(
            LessonNoteNotification.objects.filter(recipient=self.teacher, lesson_note=self.note).exists()
        )
        event.message = "Changed comment"
        with self.assertRaisesMessage(ValidationError, "immutable"):
            event.save()

    def test_version_is_immutable(self):
        version = record_initial_lesson_version(note=self.note, actor=self.teacher)
        version.reason = "Changed reason"
        with self.assertRaisesMessage(ValidationError, "immutable"):
            version.save()

    def test_teacher_cannot_open_review_queue_and_admin_can(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse("lesson_review_queue"), secure=True)
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("lesson_review_queue"), secure=True)
        self.assertEqual(response.status_code, 200)

    def test_author_can_submit_through_view(self):
        record_initial_lesson_version(note=self.note, actor=self.teacher)
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            reverse("submit_lesson_note", args=[self.note.pk]),
            {"message": "Please review"},
            secure=True,
        )
        self.assertRedirects(response, reverse("lesson_note_detail", args=[self.note.pk]), fetch_redirect_response=False)
        self.note.refresh_from_db()
        self.assertEqual(self.note.status, LessonNote.Status.PENDING_REVIEW)
