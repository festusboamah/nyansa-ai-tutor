from django.dispatch import receiver
from django.db.models.signals import pre_save

from .models import SchoolClass


@receiver(pre_save, sender=SchoolClass)
def remember_previous_class_teacher(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_class_teacher_id = None
        return
    instance._previous_class_teacher_id = sender.objects.filter(pk=instance.pk).values_list(
        "class_teacher_id", flat=True
    ).first()
