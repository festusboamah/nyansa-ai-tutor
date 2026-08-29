from datetime import date

from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from courses.models import Enrollment, Subject
from schools.models import School, SchoolMembership

from .models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, Term


class CourseEnrollmentSyncTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Sync School", slug="sync-school")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027",
            start_date=date(2026, 9, 1), end_date=date(2027, 7, 31), is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", order=1,
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15),
        )
        self.school_class = SchoolClass.objects.create(school=self.school, academic_year=self.year, name="JHS 1")
        self.maths = Subject.objects.create(school=self.school, name="Mathematics")
        self.english = Subject.objects.create(school=self.school, name="English Language")
        SubjectOffering.objects.create(
            school=self.school, school_class=self.school_class, subject=self.maths, term=self.term,
        )
        self.student_user = User.objects.create_user(username="jhs-student", password="test-password")
        self.student = SchoolMembership.objects.create(
            school=self.school, user=self.student_user, role=SchoolMembership.Role.STUDENT,
        )

    def test_joining_a_class_enrolls_in_its_subjects(self):
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.student)

        self.assertTrue(Enrollment.objects.filter(student=self.student_user, subject=self.maths).exists())

    def test_transferred_or_completed_class_enrollment_is_not_synced(self):
        ClassEnrollment.objects.create(
            school_class=self.school_class, student=self.student, status=ClassEnrollment.Status.TRANSFERRED,
        )

        self.assertFalse(Enrollment.objects.filter(student=self.student_user, subject=self.maths).exists())

    def test_leaving_a_class_does_not_remove_existing_subject_access(self):
        enrollment = ClassEnrollment.objects.create(school_class=self.school_class, student=self.student)
        self.assertTrue(Enrollment.objects.filter(student=self.student_user, subject=self.maths).exists())

        enrollment.status = ClassEnrollment.Status.TRANSFERRED
        enrollment.save(update_fields=["status"])

        self.assertTrue(Enrollment.objects.filter(student=self.student_user, subject=self.maths).exists())

    def test_a_new_subject_offering_retroactively_enrolls_existing_class_members(self):
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.student)
        self.assertFalse(Enrollment.objects.filter(student=self.student_user, subject=self.english).exists())

        SubjectOffering.objects.create(
            school=self.school, school_class=self.school_class, subject=self.english, term=self.term,
        )

        self.assertTrue(Enrollment.objects.filter(student=self.student_user, subject=self.english).exists())

    def test_does_not_duplicate_an_existing_enrollment(self):
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.student)
        # Re-saving (e.g. a status no-op update) must not error or duplicate.
        enrollment = ClassEnrollment.objects.get(school_class=self.school_class, student=self.student)
        enrollment.save()

        self.assertEqual(Enrollment.objects.filter(student=self.student_user, subject=self.maths).count(), 1)


class SyncCourseEnrollmentsCommandTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Backfill School", slug="backfill-school")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027",
            start_date=date(2026, 9, 1), end_date=date(2027, 7, 31), is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", order=1,
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15),
        )
        self.school_class = SchoolClass.objects.create(school=self.school, academic_year=self.year, name="JHS 2")
        self.subject = Subject.objects.create(school=self.school, name="Science")
        SubjectOffering.objects.create(
            school=self.school, school_class=self.school_class, subject=self.subject, term=self.term,
        )
        self.student_user = User.objects.create_user(username="pre-existing-student", password="test-password")
        self.student = SchoolMembership.objects.create(
            school=self.school, user=self.student_user, role=SchoolMembership.Role.STUDENT,
        )

    def test_backfills_students_who_predate_this_feature(self):
        # Bypass the signal to simulate data that existed before the sync feature shipped.
        from django.db.models.signals import post_save

        from .signals import sync_course_enrollments_on_class_enrollment

        post_save.disconnect(sync_course_enrollments_on_class_enrollment, sender=ClassEnrollment)
        try:
            ClassEnrollment.objects.create(school_class=self.school_class, student=self.student)
        finally:
            post_save.connect(sync_course_enrollments_on_class_enrollment, sender=ClassEnrollment)
        self.assertFalse(Enrollment.objects.filter(student=self.student_user, subject=self.subject).exists())

        call_command("sync_course_enrollments")

        self.assertTrue(Enrollment.objects.filter(student=self.student_user, subject=self.subject).exists())

    def test_command_is_idempotent(self):
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.student)

        call_command("sync_course_enrollments")
        call_command("sync_course_enrollments")

        self.assertEqual(Enrollment.objects.filter(student=self.student_user, subject=self.subject).count(), 1)
