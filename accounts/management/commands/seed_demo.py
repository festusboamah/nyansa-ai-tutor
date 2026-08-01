import os
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from academics.models import AcademicYear, SchoolClass, Term
from courses.models import Subject
from schools.models import School, SchoolMembership


class Command(BaseCommand):
    help = "Create idempotent synthetic demo records from private environment variables."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.NYANSA_DEMO_MODE:
            raise CommandError("seed_demo is available only when NYANSA_DEMO_MODE=True.")

        username = os.getenv("DEMO_ADMIN_USERNAME", "").strip()
        password = os.getenv("DEMO_ADMIN_PASSWORD", "")
        email = os.getenv("DEMO_ADMIN_EMAIL", "").strip()
        if not username or not password:
            self.stdout.write("Demo credentials are not configured; skipping demo seed.")
            return
        if len(password) < 12:
            raise CommandError("DEMO_ADMIN_PASSWORD must contain at least 12 characters.")

        school, _ = School.objects.update_or_create(
            slug="nyansa-demo-school",
            defaults={
                "name": "Nyansa Demonstration School",
                "address": "Synthetic demonstration environment",
                "email": "demo-school@example.com",
                "status": School.Status.ACTIVE,
            },
        )

        user_model = get_user_model()
        user, _ = user_model.objects.update_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": "Demo",
                "last_name": "Administrator",
                "role": user_model.Role.TEACHER,
                "is_staff": True,
                "is_active": True,
            },
        )
        user.set_password(password)
        user.save(update_fields=["password"])
        SchoolMembership.objects.update_or_create(
            school=school,
            user=user,
            defaults={
                "role": SchoolMembership.Role.SCHOOL_ADMIN,
                "status": SchoolMembership.Status.ACTIVE,
                "identifier": "DEMO-ADMIN",
            },
        )

        current_year = date.today().year
        academic_year, _ = AcademicYear.objects.update_or_create(
            school=school,
            name=f"{current_year}/{current_year + 1} Demo",
            defaults={
                "start_date": date(current_year, 1, 1),
                "end_date": date(current_year, 12, 31),
                "is_current": True,
            },
        )
        Term.objects.update_or_create(
            academic_year=academic_year,
            name="Demo Term",
            defaults={
                "order": 1,
                "start_date": date(current_year, 1, 1),
                "end_date": date(current_year, 12, 31),
            },
        )
        SchoolClass.objects.update_or_create(
            school=school,
            academic_year=academic_year,
            name="Demo Class",
            defaults={"capacity": 30},
        )
        for subject_name in ("English Language", "Mathematics", "Science"):
            Subject.objects.get_or_create(
                school=school,
                name=subject_name,
                defaults={"description": "Synthetic demonstration subject."},
            )

        self.stdout.write(self.style.SUCCESS(f"Demo data ready for administrator {username}."))
