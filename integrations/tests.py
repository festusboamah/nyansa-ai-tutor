import hashlib
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, SchoolClass, SubjectOffering, Term
from accounts.models import User
from analytics.models import EarlyWarningPolicy, RiskSignal
from courses.models import Subject
from gradebook.models import Assessment, AssessmentCategory, GradeEntry, GradeScheme
from schools.models import School, SchoolMembership

from .models import IntegrationCredential


class IntegrationsTestCase(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Integration School", slug="integration-school")
        self.admin = self._member("integration-admin", SchoolMembership.Role.SCHOOL_ADMIN)
        self.teacher = self._member("integration-teacher", SchoolMembership.Role.TEACHER)
        self.student = self._member("integration-student", SchoolMembership.Role.STUDENT)
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027", start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31), is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", order=1,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
        )
        self.school_class = SchoolClass.objects.create(
            school=self.school, academic_year=self.year, name="Basic 6"
        )
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.offering = SubjectOffering.objects.create(
            school=self.school, school_class=self.school_class, subject=self.subject, term=self.term
        )
        self.scheme = GradeScheme.objects.create(
            school=self.school, academic_year=self.year, name="Standard", status=GradeScheme.Status.ACTIVE
        )
        self.category = AssessmentCategory.objects.create(
            scheme=self.scheme, name="Coursework", code="coursework", weight=Decimal("100"), order=1
        )
        self.assessment = Assessment.objects.create(
            school=self.school, offering=self.offering, category=self.category,
            title="Fractions test", max_score=Decimal("100"), status=Assessment.Status.CLOSED,
        )
        self.entry = GradeEntry.objects.create(
            school=self.school, assessment=self.assessment, student=self.student, recorded_by=self.admin,
            score=Decimal("80"), status=GradeEntry.Status.PUBLISHED,
            review_status=GradeEntry.ReviewStatus.APPROVED, reviewed_by=self.admin,
        )

    def _member(self, username, role, school=None):
        user = User.objects.create_user(
            username=username, password="test-password",
            role=User.Role.TEACHER if role != "STUDENT" else User.Role.STUDENT,
        )
        return SchoolMembership.objects.create(school=school or self.school, user=user, role=role)

    def _login(self, membership):
        self.client.force_login(membership.user)
        session = self.client.session
        session["active_school_id"] = membership.school_id
        session.save()

    def _generate_token(self, membership=None):
        self._login(membership or self.admin)
        response = self.client.post(
            reverse("integration_credential_settings"), {"action": "generate"}, secure=True, follow=True,
        )
        messages = list(response.context["messages"])
        text = str(messages[-1])
        return text.split("New API token generated: ")[1].split(" — copy")[0]

    def _auth_headers(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


class CredentialSettingsViewTests(IntegrationsTestCase):
    def test_admin_can_generate_a_token(self):
        token = self._generate_token()

        credential = IntegrationCredential.objects.get(school=self.school)
        self.assertEqual(credential.token_hash, hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(credential.created_by, self.admin)

    def test_non_admin_cannot_access_settings(self):
        self._login(self.teacher)

        response = self.client.get(reverse("integration_credential_settings"), secure=True)

        self.assertEqual(response.status_code, 403)

    def test_regenerating_replaces_the_token(self):
        first_token = self._generate_token()
        second_token = self._generate_token()

        self.assertNotEqual(first_token, second_token)
        response = self.client.get(
            reverse("api_evidence"), {"term": self.term.pk}, secure=True, **self._auth_headers(first_token)
        )
        self.assertEqual(response.status_code, 401)


class ApiAuthTests(IntegrationsTestCase):
    def test_missing_token_returns_401(self):
        response = self.client.get(reverse("api_evidence"), {"term": self.term.pk}, secure=True)
        self.assertEqual(response.status_code, 401)

    def test_invalid_token_returns_401(self):
        response = self.client.get(
            reverse("api_evidence"), {"term": self.term.pk}, secure=True,
            **self._auth_headers("not-a-real-token"),
        )
        self.assertEqual(response.status_code, 401)

    def test_valid_token_updates_last_used_at(self):
        token = self._generate_token()
        credential = IntegrationCredential.objects.get(school=self.school)
        self.assertIsNone(credential.last_used_at)

        self.client.get(
            reverse("api_evidence"), {"term": self.term.pk}, secure=True, **self._auth_headers(token)
        )

        credential.refresh_from_db()
        self.assertIsNotNone(credential.last_used_at)


class EvidenceEndpointTests(IntegrationsTestCase):
    def test_returns_only_approved_evidence(self):
        GradeEntry.objects.create(
            school=self.school, assessment=self.assessment,
            student=self._member("draft-student", SchoolMembership.Role.STUDENT),
            recorded_by=self.admin, score=Decimal("50"), status=GradeEntry.Status.DRAFT,
        )
        token = self._generate_token()

        response = self.client.get(
            reverse("api_evidence"), {"term": self.term.pk}, secure=True, **self._auth_headers(token)
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["evidence"]), 1)
        self.assertEqual(data["evidence"][0]["student_id"], self.student.pk)
        self.assertEqual(data["evidence"][0]["score"], "80.00")

    def test_missing_term_returns_400(self):
        token = self._generate_token()

        response = self.client.get(reverse("api_evidence"), secure=True, **self._auth_headers(token))

        self.assertEqual(response.status_code, 400)

    def test_term_from_another_school_is_rejected(self):
        other_school = School.objects.create(name="Other School", slug="other-integration-school")
        other_admin = self._member("other-integration-admin", SchoolMembership.Role.SCHOOL_ADMIN, school=other_school)
        other_year = AcademicYear.objects.create(
            school=other_school, name="2026/2027", start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31), is_current=True,
        )
        other_term = Term.objects.create(
            academic_year=other_year, name="Term 1", order=1,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
        )
        token = self._generate_token()

        response = self.client.get(
            reverse("api_evidence"), {"term": other_term.pk}, secure=True, **self._auth_headers(token)
        )

        self.assertEqual(response.status_code, 400)


class MasterySummaryEndpointTests(IntegrationsTestCase):
    def test_returns_flattened_mastery_summary(self):
        from mastery.models import Strand, Topic

        strand = Strand.objects.create(school=self.school, subject=self.subject, name="Number", order=1)
        Topic.objects.create(strand=strand, name="Fractions", order=1)
        token = self._generate_token()

        response = self.client.get(
            reverse("api_mastery_summary"),
            {"term": self.term.pk, "class_id": self.school_class.pk, "subject_id": self.subject.pk},
            secure=True, **self._auth_headers(token),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["strands"][0]["strand"]["name"], "Number")
        self.assertEqual(data["strands"][0]["topics"][0]["topic"]["name"], "Fractions")

    def test_class_from_another_school_returns_404(self):
        other_school = School.objects.create(name="Other School", slug="other-mastery-school")
        other_year = AcademicYear.objects.create(
            school=other_school, name="2026/2027", start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31), is_current=True,
        )
        other_class = SchoolClass.objects.create(school=other_school, academic_year=other_year, name="Other Class")
        token = self._generate_token()

        response = self.client.get(
            reverse("api_mastery_summary"),
            {"term": self.term.pk, "class_id": other_class.pk, "subject_id": self.subject.pk},
            secure=True, **self._auth_headers(token),
        )

        self.assertEqual(response.status_code, 404)

    def test_subject_from_another_school_returns_404(self):
        other_school = School.objects.create(name="Other Subject School", slug="other-subject-school")
        other_subject = Subject.objects.create(school=other_school, name="Mathematics")
        token = self._generate_token()

        response = self.client.get(
            reverse("api_mastery_summary"),
            {"term": self.term.pk, "class_id": self.school_class.pk, "subject_id": other_subject.pk},
            secure=True, **self._auth_headers(token),
        )

        self.assertEqual(response.status_code, 404)


class RiskSignalsEndpointTests(IntegrationsTestCase):
    def test_excludes_resolved_signals(self):
        policy = EarlyWarningPolicy.objects.create(
            school=self.school, name="Low average", metric=EarlyWarningPolicy.Metric.LOW_AVERAGE,
            threshold=Decimal("55"), created_by=self.admin,
        )
        open_signal = RiskSignal.objects.create(
            school=self.school, policy=policy, student=self.student, school_class=self.school_class,
            term=self.term, observed_value=Decimal("40"), status=RiskSignal.Status.OPEN,
        )
        RiskSignal.objects.create(
            school=self.school, policy=policy,
            student=self._member("resolved-student", SchoolMembership.Role.STUDENT),
            school_class=self.school_class, term=self.term, observed_value=Decimal("40"),
            status=RiskSignal.Status.RESOLVED,
        )
        token = self._generate_token()

        response = self.client.get(
            reverse("api_risk_signals"), {"term": self.term.pk}, secure=True, **self._auth_headers(token)
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["signals"]), 1)
        self.assertEqual(data["signals"][0]["student_id"], open_signal.student_id)
