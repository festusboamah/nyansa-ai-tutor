from datetime import date
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from accounts.models import User
from courses.models import Subject
from communications.models import Notification
from schools.models import School, SchoolMembership
from .models import AcademicYear, SchoolClass, SubjectOffering, TeacherAssignment, Term


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

    def _teacher_and_offering(self):
        user = User.objects.create_user(username="assigned-teacher", password="test-password")
        teacher = SchoolMembership.objects.create(
            school=self.school, user=user, role=SchoolMembership.Role.TEACHER
        )
        term = Term.objects.create(
            academic_year=self.year, name="First Term", order=1,
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15),
        )
        school_class = SchoolClass.objects.create(school=self.school, academic_year=self.year, name="JHS 1")
        subject = Subject.objects.create(school=self.school, name="Mathematics")
        offering = SubjectOffering.objects.create(
            school=self.school, school_class=school_class, subject=subject, term=term
        )
        return teacher, school_class, offering

    def test_subject_assignment_notifies_teacher_once(self):
        teacher, _school_class, offering = self._teacher_and_offering()
        assignment = TeacherAssignment.objects.create(offering=offering, teacher=teacher, is_lead=True)
        notification = Notification.objects.get(recipient=teacher, kind=Notification.Kind.STAFF_ASSIGNMENT)
        self.assertIn("Mathematics", notification.message)
        self.assertIn("JHS 1", notification.message)
        self.assertEqual(notification.target_url, f"/gradebook/offerings/{offering.id}/")
        assignment.save()
        self.assertEqual(Notification.objects.filter(recipient=teacher).count(), 1)

    def test_class_teacher_change_notifies_new_and_previous_teacher(self):
        first, school_class, _offering = self._teacher_and_offering()
        second_user = User.objects.create_user(username="second-teacher", password="test-password")
        second = SchoolMembership.objects.create(
            school=self.school, user=second_user, role=SchoolMembership.Role.TEACHER
        )
        school_class.class_teacher = first
        school_class.save(update_fields=["class_teacher"])
        self.assertTrue(Notification.objects.filter(recipient=first, title="New class-teacher assignment").exists())
        school_class.class_teacher = second
        school_class.save(update_fields=["class_teacher"])
        self.assertTrue(Notification.objects.filter(recipient=second, title="New class-teacher assignment").exists())
        self.assertTrue(Notification.objects.filter(recipient=first, title="Class-teacher assignment changed").exists())

    def test_deleted_subject_assignment_notifies_teacher(self):
        teacher, _school_class, offering = self._teacher_and_offering()
        assignment = TeacherAssignment.objects.create(offering=offering, teacher=teacher)
        assignment.delete()
        self.assertTrue(Notification.objects.filter(recipient=teacher, title="Subject assignment removed").exists())
