from django.core.management.base import BaseCommand

from academics.models import ClassEnrollment
from academics.signals import enroll_student_in_class_subjects


class Command(BaseCommand):
    help = (
        "Backfills courses.Enrollment for every student already in a class today, "
        "for every subject their class offers. Additive and idempotent (uses "
        "get_or_create) - safe to run on every deploy, same as ensure_superuser. "
        "New class-joins and new subject offerings are kept in sync automatically "
        "going forward by academics/signals.py; this only catches up existing data."
    )

    def handle(self, *args, **options):
        enrollments = ClassEnrollment.objects.filter(
            status=ClassEnrollment.Status.ACTIVE
        ).select_related("student__user", "school_class")
        for class_enrollment in enrollments:
            enroll_student_in_class_subjects(class_enrollment)
        self.stdout.write(f"Synced course enrollments for {enrollments.count()} active class enrollment(s).")
