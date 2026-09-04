from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from courses.models import Subject
from schools.models import School, SchoolMembership

from .models import AcademicYear, CourseEnrollment, CourseSection, Term


class CourseSectionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Nyansa University", slug="nyansa-university",
            education_system=School.EducationSystem.TERTIARY,
        )
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027",
            start_date=date(2026, 9, 1), end_date=date(2027, 7, 31), is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Semester 1", order=1,
            start_date=date(2026, 9, 1), end_date=date(2027, 1, 15),
        )
        self.course = Subject.objects.create(
            school=self.school, name="Introduction to Computer Science", code="CS101", credit_hours=3,
        )
        self.teacher_user = User.objects.create_user(username="lecturer", password="test-password")
        self.teacher = SchoolMembership.objects.create(
            school=self.school, user=self.teacher_user, role=SchoolMembership.Role.TEACHER,
        )
        self.student_user = User.objects.create_user(username="undergrad", password="test-password")
        self.student = SchoolMembership.objects.create(
            school=self.school, user=self.student_user, role=SchoolMembership.Role.STUDENT,
        )

    def test_creates_a_section_with_an_instructor(self):
        section = CourseSection.objects.create(
            school=self.school, subject=self.course, term=self.term,
            section_code="A", instructor=self.teacher, capacity=40,
        )
        section.full_clean()

        self.assertEqual(str(section), "Introduction to Computer Science A — Semester 1")

    def test_duplicate_section_code_for_same_course_and_term_is_rejected(self):
        CourseSection.objects.create(school=self.school, subject=self.course, term=self.term, section_code="A")

        with self.assertRaises(IntegrityError), transaction.atomic():
            CourseSection.objects.create(school=self.school, subject=self.course, term=self.term, section_code="A")

    def test_section_from_another_school_fails_validation(self):
        other_school = School.objects.create(name="Other University", slug="other-university")
        section = CourseSection(school=other_school, subject=self.course, term=self.term, section_code="A")

        with self.assertRaises(ValidationError):
            section.full_clean()

    def test_instructor_must_be_a_teacher_in_the_same_school(self):
        section = CourseSection(school=self.school, subject=self.course, term=self.term, section_code="A", instructor=self.student)

        with self.assertRaises(ValidationError):
            section.full_clean()

    def test_enrolling_a_student_in_a_section(self):
        section = CourseSection.objects.create(school=self.school, subject=self.course, term=self.term, section_code="A")

        enrollment = CourseEnrollment.objects.create(student=self.student, section=section)

        self.assertEqual(enrollment.status, CourseEnrollment.Status.ACTIVE)

    def test_duplicate_enrollment_in_the_same_section_is_rejected(self):
        section = CourseSection.objects.create(school=self.school, subject=self.course, term=self.term, section_code="A")
        CourseEnrollment.objects.create(student=self.student, section=section)

        with self.assertRaises(IntegrityError), transaction.atomic():
            CourseEnrollment.objects.create(student=self.student, section=section)

    def test_a_teacher_membership_cannot_be_used_as_a_student_enrollment(self):
        section = CourseSection.objects.create(school=self.school, subject=self.course, term=self.term, section_code="A")
        enrollment = CourseEnrollment(student=self.teacher, section=section)

        with self.assertRaises(ValidationError):
            enrollment.full_clean()

    def test_dropping_a_course_changes_status_without_deleting_the_record(self):
        section = CourseSection.objects.create(school=self.school, subject=self.course, term=self.term, section_code="A")
        enrollment = CourseEnrollment.objects.create(student=self.student, section=section)

        enrollment.status = CourseEnrollment.Status.DROPPED
        enrollment.save(update_fields=["status"])

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, CourseEnrollment.Status.DROPPED)
