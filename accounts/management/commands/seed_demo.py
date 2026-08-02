import os
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from django.utils import timezone

from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, TeacherAssignment, Term
from analytics.models import EarlyWarningPolicy, RiskSignal
from attendance.models import AttendanceRecord, AttendanceSession
from courses.models import Subject
from dashboard.lesson_workflow import record_initial_lesson_version, submit_lesson_note
from dashboard.models import LessonNote, LessonNoteEvent, LessonNoteNotification, LessonNoteVersion
from finance.models import Charge, FeeItem, FeeStructure
from gradebook.models import Assessment, AssessmentCategory, GradeEntry, GradeScheme
from guardians.models import GuardianLink
from reports.models import TermReport
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
                "offers_kg": True,
                "offers_primary": True,
                "offers_jhs": True,
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
        admin, _ = SchoolMembership.objects.update_or_create(
            school=school,
            user=user,
            defaults={
                "role": SchoolMembership.Role.SCHOOL_ADMIN,
                "status": SchoolMembership.Status.ACTIVE,
                "identifier": "DEMO-ADMIN",
            },
        )

        current_year = date.today().year
        demo_year_name = f"{current_year}/{current_year + 1} Demo"
        has_administrator_current_year = AcademicYear.objects.filter(
            school=school, is_current=True
        ).exclude(name=demo_year_name).exists()
        academic_year, _ = AcademicYear.objects.update_or_create(
            school=school,
            name=demo_year_name,
            defaults={
                "start_date": date(current_year, 1, 1),
                "end_date": date(current_year, 12, 31),
                # Demo seeding must never override a year selected by the administrator.
                "is_current": not has_administrator_current_year,
            },
        )
        term, _ = Term.objects.update_or_create(
            academic_year=academic_year,
            name="Demo Term",
            defaults={
                "order": 1,
                "start_date": date(current_year, 1, 1),
                "end_date": date(current_year, 12, 31),
            },
        )
        school_class, _ = SchoolClass.objects.update_or_create(
            school=school,
            academic_year=academic_year,
            name="Demo Class",
            defaults={"capacity": 30},
        )
        def demo_member(username, first_name, last_name, role, identifier, email=""):
            member_user, _ = user_model.objects.update_or_create(
                username=username,
                defaults={"first_name": first_name, "last_name": last_name, "email": email,
                          "role": user_model.Role.TEACHER if role == SchoolMembership.Role.TEACHER else user_model.Role.STUDENT,
                          "is_active": True},
            )
            member_user.set_password(password)
            member_user.save(update_fields=["password"])
            membership, _ = SchoolMembership.objects.update_or_create(
                school=school, user=member_user,
                defaults={"role": role, "status": SchoolMembership.Status.ACTIVE, "identifier": identifier},
            )
            return membership

        teacher = demo_member("demo-teacher", "Ama", "Mensah", SchoolMembership.Role.TEACHER, "T-001")
        guardian = demo_member("demo-guardian", "Kwame", "Owusu", SchoolMembership.Role.PARENT, "P-001", "guardian@example.com")
        students = [
            demo_member("demo-student", "Akosua", "Owusu", SchoolMembership.Role.STUDENT, "ST-001"),
            demo_member("demo-student-2", "Kojo", "Asare", SchoolMembership.Role.STUDENT, "ST-002"),
        ]
        school_class.class_teacher = teacher
        school_class.save(update_fields=["class_teacher"])
        for student in students:
            ClassEnrollment.objects.update_or_create(school_class=school_class, student=student, defaults={"status": ClassEnrollment.Status.ACTIVE})

        GuardianLink.objects.update_or_create(
            school=school, guardian=guardian, student=students[0],
            defaults={"relationship": GuardianLink.Relationship.GUARDIAN, "status": GuardianLink.Status.ACTIVE,
                      "is_primary_contact": True, "authorization_reference": "DEMO-CONSENT-001", "authorized_by": admin},
        )

        scheme, _ = GradeScheme.objects.update_or_create(
            school=school, academic_year=academic_year, name="Demo Standard",
            defaults={"status": GradeScheme.Status.ACTIVE},
        )
        category, _ = AssessmentCategory.objects.update_or_create(
            scheme=scheme, code="term-work", defaults={"name": "Term Work", "weight": Decimal("100"), "order": 1},
        )
        subjects = []
        for subject_name in ("English Language", "Mathematics", "Science"):
            subject, _ = Subject.objects.get_or_create(
                school=school,
                name=subject_name,
                defaults={"description": "Synthetic demonstration subject."},
            )
            subjects.append(subject)
            offering, _ = SubjectOffering.objects.get_or_create(school=school, school_class=school_class, subject=subject, term=term)
            TeacherAssignment.objects.update_or_create(offering=offering, teacher=teacher, defaults={"is_lead": True})
            assessment, _ = Assessment.objects.update_or_create(
                school=school, offering=offering, category=category, title="Demo Assessment",
                defaults={"max_score": Decimal("100"), "status": Assessment.Status.CLOSED},
            )
            for index, student in enumerate(students):
                GradeEntry.objects.update_or_create(
                    assessment=assessment, student=student,
                    defaults={"school": school, "recorded_by": teacher, "score": Decimal(78 - index * 14),
                              "source": GradeEntry.Source.MANUAL, "status": GradeEntry.Status.PUBLISHED,
                              "review_status": GradeEntry.ReviewStatus.APPROVED, "reviewed_by": admin,
                              "reviewed_at": timezone.now(), "review_note": "Synthetic demonstration grade."},
                )

        lesson_note, lesson_created = LessonNote.objects.get_or_create(
            teacher=teacher.user,
            subject=subjects[2],
            week_ending=date(current_year, 6, 5),
            strand_topic="Living things and their environment",
            defaults={
                "class_level": school_class.name,
                "content_standard": "Understand relationships between living things and their environment.",
                "learning_indicator": "Classify living things and explain one habitat relationship.",
                "performance_indicator": "Learners accurately classify examples and justify their choices.",
                "reference": "Synthetic curriculum demonstration",
                "resources": "Picture cards, leaves, and a school-environment checklist",
                "num_days": 3,
                "generated_content": '{"days":[{"day":"Monday","starter":"Observe school surroundings","main":"Classify living and non-living examples","reflection":"Explain one classification"},{"day":"Wednesday","starter":"Review classifications","main":"Map organisms to habitats","reflection":"Share one habitat relationship"},{"day":"Friday","starter":"Quick retrieval quiz","main":"Small-group environment audit","reflection":"Record one action to protect a habitat"}]}',
            },
        )
        if lesson_created or lesson_note.current_version == 0:
            record_initial_lesson_version(note=lesson_note, actor=teacher)
            submit_lesson_note(
                note=lesson_note,
                actor=teacher,
                message="Synthetic lesson plan ready for administrator review.",
            )

        for offset, record_status in enumerate(("PRESENT", "PRESENT", "ABSENT"), start=1):
            attendance_date = date(current_year, 1, offset + 1)
            session, _ = AttendanceSession.objects.update_or_create(
                school_class=school_class, attendance_date=attendance_date,
                defaults={"school": school, "term": term, "status": AttendanceSession.Status.SUBMITTED,
                          "submitted_by": teacher, "submitted_at": timezone.now()},
            )
            for index, student in enumerate(students):
                AttendanceRecord.objects.update_or_create(
                    session=session, student=student,
                    defaults={"status": record_status if index == 0 else AttendanceRecord.Status.PRESENT, "marked_by": teacher},
                )

        TermReport.objects.update_or_create(
            school_class=school_class, term=term, student=students[0],
            defaults={"school": school, "status": TermReport.Status.PUBLISHED, "prepared_by": teacher,
                      "reviewed_by": admin, "average_score": Decimal("78"), "total_score": Decimal("234"),
                      "teacher_remark": "A steady synthetic demonstration performance.",
                      "administrator_remark": "Continue the positive effort.",
                      "promotion_outcome": TermReport.Promotion.PROMOTED,
                      "snapshot": {"average": "78.00", "note": "Synthetic demonstration report"},
                      "submitted_at": timezone.now(), "reviewed_at": timezone.now(), "published_at": timezone.now()},
        )

        structure, _ = FeeStructure.objects.update_or_create(
            school=school, term=term, school_class=school_class, name="Demo Term Fees", version=1,
            defaults={"status": FeeStructure.Status.ACTIVE, "created_by": admin},
        )
        fee_item, _ = FeeItem.objects.update_or_create(
            structure=structure, code="demo-tuition",
            defaults={"name": "Tuition", "amount": Decimal("500"), "due_date": date(current_year, 6, 30)},
        )
        for student in students:
            Charge.objects.get_or_create(school=school, student=student, fee_item=fee_item,
                                         defaults={"amount": fee_item.amount, "posted_by": admin})

        policy, _ = EarlyWarningPolicy.objects.update_or_create(
            school=school, name="Demo attendance follow-up",
            defaults={"metric": EarlyWarningPolicy.Metric.LOW_ATTENDANCE, "threshold": Decimal("80"),
                      "is_active": True, "created_by": admin},
        )
        RiskSignal.objects.update_or_create(
            policy=policy, student=students[0], school_class=school_class, term=term,
            defaults={"school": school, "observed_value": Decimal("66.67"),
                      "evidence": {"source": "Submitted attendance register", "period": term.name,
                                   "rule": "Attendance below 80%"}, "status": RiskSignal.Status.OPEN},
        )

        self.stdout.write(self.style.SUCCESS(
            f"Complete synthetic demo ready. Accounts: {username}, demo-teacher, demo-guardian, demo-student."
        ))
