"""Notification receivers for domain events fired by other apps.

communications subscribes to events from academics/gradebook rather than
those apps importing communications - this keeps the core teaching/learning
apps free of any dependency on the notification app.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from academics.models import SchoolClass, TeacherAssignment
from dashboard.signals import lesson_note_author_notified, lesson_note_needs_review
from gradebook.signals import grade_entry_published, grade_review_decided
from quizzes.models import AssignmentSubmission
from schools.models import SchoolMembership

from .models import Notification
from .services import create_notification, notify_school_role


@receiver(post_save, sender=TeacherAssignment)
def notify_subject_teacher(sender, instance, created, **kwargs):
    if not created:
        return
    offering = instance.offering
    create_notification(
        recipient=instance.teacher,
        kind=Notification.Kind.STAFF_ASSIGNMENT,
        title="New subject assignment",
        message=(
            f"You have been assigned {offering.subject.name} for "
            f"{offering.school_class.name} — {offering.term.name}."
            + (" You are the lead teacher." if instance.is_lead else "")
        ),
        target_url=f"/gradebook/offerings/{offering.id}/",
        deduplication_key=f"teacher-assignment:{instance.id}:created",
    )


@receiver(post_delete, sender=TeacherAssignment)
def notify_subject_assignment_removed(sender, instance, **kwargs):
    offering = instance.offering
    create_notification(
        recipient=instance.teacher,
        kind=Notification.Kind.STAFF_ASSIGNMENT,
        title="Subject assignment removed",
        message=f"Your {offering.subject.name} assignment for {offering.school_class.name} — {offering.term.name} was removed.",
        target_url="/dashboard/",
        deduplication_key=f"teacher-assignment:{instance.id}:removed",
    )


@receiver(post_save, sender=SchoolClass)
def notify_class_teacher(sender, instance, **kwargs):
    previous_id = getattr(instance, "_previous_class_teacher_id", None)
    if instance.class_teacher_id and instance.class_teacher_id != previous_id:
        create_notification(
            recipient=instance.class_teacher,
            kind=Notification.Kind.STAFF_ASSIGNMENT,
            title="New class-teacher assignment",
            message=f"You have been assigned as class teacher for {instance.name} — {instance.academic_year.name}.",
            target_url="/attendance/",
            deduplication_key=f"class-teacher:{instance.id}:{instance.class_teacher_id}",
        )
    if previous_id and previous_id != instance.class_teacher_id:
        previous = instance.school.memberships.filter(pk=previous_id).first()
        if previous:
            create_notification(
                recipient=previous,
                kind=Notification.Kind.STAFF_ASSIGNMENT,
                title="Class-teacher assignment changed",
                message=f"You are no longer the class teacher for {instance.name} — {instance.academic_year.name}.",
                target_url="/dashboard/",
                deduplication_key=f"class-teacher:{instance.id}:{previous_id}:removed",
            )


@receiver(grade_entry_published)
def notify_admins_of_pending_grade(sender, entry, actor, **kwargs):
    notify_school_role(
        school=entry.school,
        role=SchoolMembership.Role.SCHOOL_ADMIN,
        kind=Notification.Kind.GRADE_REVIEW,
        title="Grade awaiting approval",
        message=f"{actor.user.username} published a grade for {entry.student.user.get_full_name() or entry.student.user.username}.",
        target_url="/gradebook/review/",
        deduplication_key=f"grade:{entry.id}:pending:{entry.updated_at.isoformat()}",
    )


@receiver(grade_review_decided)
def notify_teacher_of_review_decision(sender, entry, note, **kwargs):
    if not entry.recorded_by_id:
        return
    create_notification(
        recipient=entry.recorded_by,
        kind=Notification.Kind.GRADE_REVIEW,
        title="Grade review completed",
        message=f"A grade was {entry.get_review_status_display().lower()}." + (f" {note}" if note else ""),
        target_url="/gradebook/",
        deduplication_key=f"grade:{entry.id}:decision:{entry.review_status}:{entry.reviewed_at.isoformat()}",
    )


@receiver(post_save, sender=AssignmentSubmission)
def notify_teacher_of_assignment_submission(sender, instance, created, **kwargs):
    if not created:
        return
    assignment = instance.assignment
    teacher_membership = SchoolMembership.objects.filter(
        school=assignment.subject.school, user=assignment.teacher,
        role=SchoolMembership.Role.TEACHER, status=SchoolMembership.Status.ACTIVE,
    ).first()
    if teacher_membership:
        create_notification(
            recipient=teacher_membership,
            kind=Notification.Kind.ASSIGNMENT,
            title="New assignment submission",
            message=f"{instance.student.get_full_name() or instance.student.username} submitted {assignment.title}.",
            target_url="/dashboard/",
            deduplication_key=f"assignment-submission:{instance.id}",
        )


def _lesson_note_author_membership(note):
    return SchoolMembership.objects.filter(
        school=note.subject.school, user=note.teacher,
        role=SchoolMembership.Role.TEACHER, status=SchoolMembership.Status.ACTIVE,
    ).first()


@receiver(lesson_note_needs_review)
def notify_reviewers_of_lesson_note(sender, note, message, **kwargs):
    notify_school_role(
        school=note.subject.school,
        role=SchoolMembership.Role.SCHOOL_ADMIN,
        kind=Notification.Kind.LESSON_REVIEW,
        title="Lesson note awaiting review",
        message=message,
        target_url="/dashboard/lesson-review/",
        deduplication_key=f"lesson:{note.id}:review:{note.current_version}:{note.status}",
    )


@receiver(lesson_note_author_notified)
def notify_author_of_lesson_note(sender, note, message, **kwargs):
    recipient = _lesson_note_author_membership(note)
    if recipient:
        create_notification(
            recipient=recipient,
            kind=Notification.Kind.LESSON_REVIEW,
            title="Lesson note review update",
            message=message,
            target_url="/dashboard/lesson-notes/",
            deduplication_key=f"lesson:{note.id}:author:{note.current_version}:{note.status}",
        )
