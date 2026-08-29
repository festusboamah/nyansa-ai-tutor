from django.dispatch import receiver
from django.db.models.signals import post_save, pre_save

from .models import ClassEnrollment, SchoolClass, SubjectOffering


@receiver(pre_save, sender=SchoolClass)
def remember_previous_class_teacher(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_class_teacher_id = None
        return
    instance._previous_class_teacher_id = sender.objects.filter(pk=instance.pk).values_list(
        "class_teacher_id", flat=True
    ).first()


def enroll_student_in_class_subjects(class_enrollment):
    """
    Bridges academics.ClassEnrollment (which class a student is in) to
    courses.Enrollment (which subjects a student can see materials/quizzes/
    assignments for) - the two have no other connection anywhere in the
    codebase, so being added to a class never used to grant subject access.
    Additive only: never removes an Enrollment, even if the ClassEnrollment
    later becomes inactive - leaving a class shouldn't silently take away
    access to work already in progress.
    """
    from courses.models import Enrollment

    subject_ids = SubjectOffering.objects.filter(
        school_class=class_enrollment.school_class
    ).values_list("subject_id", flat=True).distinct()
    for subject_id in subject_ids:
        Enrollment.objects.get_or_create(student=class_enrollment.student.user, subject_id=subject_id)


@receiver(post_save, sender=ClassEnrollment)
def sync_course_enrollments_on_class_enrollment(sender, instance, **kwargs):
    if instance.status == ClassEnrollment.Status.ACTIVE:
        enroll_student_in_class_subjects(instance)


@receiver(post_save, sender=SubjectOffering)
def sync_course_enrollments_on_new_offering(sender, instance, created, **kwargs):
    if not created:
        return
    from courses.models import Enrollment

    student_users = ClassEnrollment.objects.filter(
        school_class=instance.school_class, status=ClassEnrollment.Status.ACTIVE,
    ).values_list("student__user", flat=True)
    for user_id in student_users:
        Enrollment.objects.get_or_create(student_id=user_id, subject_id=instance.subject_id)
