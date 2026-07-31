from datetime import date
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from accounts.models import User
from courses.models import Subject
from schools.models import School, SchoolMembership
from .models import AcademicYear, SchoolClass, SubjectOffering, Term


class AcademicStructureTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Nyansa School", slug="nyansa-school")
        self.year = AcademicYear.objects.create(school=self.school, name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 7, 31), is_current=True)

    def test_only_one_current_year_per_school(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcademicYear.objects.create(school=self.school, name="2027/2028", start_date=date(2027, 9, 1), end_date=date(2028, 7, 31), is_current=True)

    def test_term_must_fit_inside_academic_year(self):
        term = Term(academic_year=self.year, name="Term 1", order=1, start_date=date(2026, 8, 1), end_date=date(2026, 12, 1))
        with self.assertRaises(ValidationError):
            term.full_clean()

    def test_subject_offering_rejects_cross_school_records(self):
        other = School.objects.create(name="Other School", slug="other-school")
        subject = Subject.objects.create(school=other, name="Mathematics")
        school_class = SchoolClass.objects.create(school=self.school, academic_year=self.year, name="JHS 1")
        term = Term.objects.create(academic_year=self.year, name="Term 1", order=1, start_date=date(2026, 9, 1), end_date=date(2026, 12, 15))
        offering = SubjectOffering(school=self.school, school_class=school_class, subject=subject, term=term)
        with self.assertRaises(ValidationError):
            offering.full_clean()

    def test_class_teacher_must_be_school_member(self):
        other = School.objects.create(name="Other School", slug="other-school")
        user = User.objects.create_user(username="teacher", password="test-password")
        membership = SchoolMembership.objects.create(school=other, user=user, role=SchoolMembership.Role.TEACHER)
        school_class = SchoolClass(school=self.school, academic_year=self.year, name="JHS 2", class_teacher=membership)
        with self.assertRaises(ValidationError):
            school_class.full_clean()
