from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, ClassEnrollment, SchoolClass
from accounts.models import User
from schools.models import School, SchoolMembership

from .models import GuardianLink
from .services import authorize_link, guardian_can_access, linked_students, revoke_link


class GuardianAccessTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Family School", slug="family-school")
        self.admin = self._member("family-admin", SchoolMembership.Role.SCHOOL_ADMIN)
        self.guardian = self._member("verified-parent", SchoolMembership.Role.PARENT, "parent@example.com")
        self.other_guardian = self._member("other-parent", SchoolMembership.Role.PARENT, "other@example.com")
        self.student = self._member("linked-student", SchoolMembership.Role.STUDENT)
        self.other_student = self._member("unlinked-student", SchoolMembership.Role.STUDENT)
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027", start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31), is_current=True,
        )
        self.school_class = SchoolClass.objects.create(
            school=self.school, academic_year=self.year, name="Basic 4"
        )
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.student)
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.other_student)
        self.link = authorize_link(
            school=self.school, guardian=self.guardian, student=self.student,
            relationship=GuardianLink.Relationship.GUARDIAN, is_primary_contact=True,
            authorization_reference="CONSENT-2026-001", actor=self.admin,
        )

    def _member(self, username, role, email=""):
        user = User.objects.create_user(username=username, email=email, password="test-password")
        return SchoolMembership.objects.create(school=self.school, user=user, role=role)

    def _login_guardian(self, guardian=None):
        guardian = guardian or self.guardian
        self.client.force_login(guardian.user)
        session = self.client.session
        session["active_school_id"] = self.school.pk
        session.save()

    def test_access_is_based_only_on_active_explicit_links(self):
        self.assertEqual(list(linked_students(self.guardian)), [self.student])
        self.assertTrue(guardian_can_access(self.guardian, self.student))
        self.assertFalse(guardian_can_access(self.guardian, self.other_student))

    def test_guardian_cannot_open_unlinked_student(self):
        self._login_guardian()
        response = self.client.get(
            reverse("guardian_student_detail", args=[self.other_student.pk]), secure=True
        )
        self.assertEqual(response.status_code, 404)

    def test_revocation_removes_portal_access_immediately(self):
        revoke_link(link=self.link, actor=self.admin)
        self.assertFalse(guardian_can_access(self.guardian, self.student))
        self.link.refresh_from_db()
        self.assertEqual(self.link.status, GuardianLink.Status.REVOKED)
        self.assertIsNotNone(self.link.revoked_at)

    def test_non_admin_cannot_authorize_or_revoke(self):
        with self.assertRaises(PermissionDenied):
            authorize_link(
                school=self.school, guardian=self.other_guardian, student=self.other_student,
                relationship=GuardianLink.Relationship.OTHER, is_primary_contact=False,
                authorization_reference="REF-2", actor=self.guardian,
            )
        with self.assertRaises(PermissionDenied):
            revoke_link(link=self.link, actor=self.guardian)

    def test_cross_school_relationship_is_rejected(self):
        other_school = School.objects.create(name="Other", slug="other-guardian-school")
        user = User.objects.create_user(username="foreign-student", password="test-password")
        foreign_student = SchoolMembership.objects.create(
            school=other_school, user=user, role=SchoolMembership.Role.STUDENT
        )
        with self.assertRaises(ValidationError):
            authorize_link(
                school=self.school, guardian=self.guardian, student=foreign_student,
                relationship=GuardianLink.Relationship.GUARDIAN, is_primary_contact=False,
                authorization_reference="BAD-REF", actor=self.admin,
            )

