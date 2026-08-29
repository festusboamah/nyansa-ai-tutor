from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.models import User

from .models import School, SchoolInvitation, SchoolMembership
from .staff_import import import_staff_invitations, parse_staff_invite_list


def _csv(text):
    return SimpleUploadedFile("staff.csv", text.encode("utf-8"), content_type="text/csv")


class ParseStaffInviteListTests(TestCase):
    def test_parses_valid_rows(self):
        records, errors = parse_staff_invite_list(_csv(
            "email,role\nama@example.com,TEACHER\nkwame@example.com,Parent/Guardian\n"
        ))

        self.assertEqual(errors, [])
        self.assertEqual(records, [
            {"email": "ama@example.com", "role": "TEACHER"},
            {"email": "kwame@example.com", "role": "PARENT"},
        ])

    def test_missing_required_headers_raises(self):
        with self.assertRaises(ValidationError):
            parse_staff_invite_list(_csv("name,email\nAma,ama@example.com\n"))

    def test_flags_invalid_email_and_role(self):
        records, errors = parse_staff_invite_list(_csv(
            "email,role\nnot-an-email,TEACHER\nama@example.com,ASTRONAUT\n"
        ))

        self.assertTrue(any("valid email" in e for e in errors))
        self.assertTrue(any("role must be one of" in e for e in errors))

    def test_flags_duplicate_email_within_file(self):
        records, errors = parse_staff_invite_list(_csv(
            "email,role\nama@example.com,TEACHER\nama@example.com,SCHOOL_ADMIN\n"
        ))

        self.assertTrue(any("duplicate email" in e for e in errors))

    def test_empty_file_is_an_error(self):
        records, errors = parse_staff_invite_list(_csv("email,role\n"))
        self.assertIn("The file contains no rows.", errors)


class ImportStaffInvitationsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Invite School", slug="invite-school")
        admin_user = User.objects.create_user(username="inviter", password="test-password")
        self.admin = SchoolMembership.objects.create(
            school=self.school, user=admin_user, role=SchoolMembership.Role.SCHOOL_ADMIN,
        )
        self.request = RequestFactory().get("/")
        self.request.school = self.school

    def test_sends_one_invitation_email_per_row(self):
        records = [{"email": "ama@example.com", "role": "TEACHER"}, {"email": "kwame@example.com", "role": "PARENT"}]

        results = import_staff_invitations(
            school=self.school, records=records, invited_by=self.admin.user, request=self.request,
        )

        self.assertEqual([r["status"] for r in results], ["invited", "invited"])
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(SchoolInvitation.objects.filter(school=self.school).count(), 2)

    def test_skips_email_with_an_existing_pending_invite(self):
        from .services import create_invitation
        create_invitation(school=self.school, email="ama@example.com", role="TEACHER", invited_by=self.admin.user)
        mail.outbox.clear()

        results = import_staff_invitations(
            school=self.school, records=[{"email": "ama@example.com", "role": "TEACHER"}],
            invited_by=self.admin.user, request=self.request,
        )

        self.assertEqual(results[0]["status"], "already_pending")
        self.assertEqual(len(mail.outbox), 0)

    def test_skips_email_already_a_member(self):
        existing_user = User.objects.create_user(username="existing", email="ama@example.com", password="x")
        SchoolMembership.objects.create(school=self.school, user=existing_user, role=SchoolMembership.Role.TEACHER)

        results = import_staff_invitations(
            school=self.school, records=[{"email": "ama@example.com", "role": "TEACHER"}],
            invited_by=self.admin.user, request=self.request,
        )

        self.assertEqual(results[0]["status"], "already_member")
        self.assertEqual(len(mail.outbox), 0)


class BulkStaffImportViewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="View Invite School", slug="view-invite-school")
        self.admin_user = User.objects.create_user(username="view-admin", password="test-password")
        SchoolMembership.objects.create(school=self.school, user=self.admin_user, role=SchoolMembership.Role.SCHOOL_ADMIN)
        self.student_user = User.objects.create_user(username="view-student", password="test-password")
        SchoolMembership.objects.create(school=self.school, user=self.student_user, role=SchoolMembership.Role.STUDENT)

    def test_non_admin_cannot_access(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("bulk_staff_import"), secure=True)
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_upload_previews_then_confirm_sends_invitations(self):
        self.client.force_login(self.admin_user)

        preview_response = self.client.post(
            reverse("bulk_staff_import"),
            {"invite_file": _csv("email,role\nama@example.com,TEACHER\n")},
            secure=True,
        )
        self.assertContains(preview_response, "ama@example.com")
        self.assertEqual(len(mail.outbox), 0)  # not sent until confirmed

        confirm_response = self.client.post(
            reverse("bulk_staff_import"), {"action": "confirm"}, secure=True, follow=True,
        )
        self.assertContains(confirm_response, "1 invitation(s) sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(SchoolInvitation.objects.filter(school=self.school, email="ama@example.com").exists())
