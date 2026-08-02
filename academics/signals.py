from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from communications.models import Notification
from communications.services import create_notification

from .models import SchoolClass, TeacherAssignment


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


@receiver(pre_save, sender=SchoolClass)
def remember_previous_class_teacher(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_class_teacher_id = None
        return
    instance._previous_class_teacher_id = sender.objects.filter(pk=instance.pk).values_list(
        "class_teacher_id", flat=True
    ).first()


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
