from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config.settings import database_from_url
from schools.models import School, SchoolMembership


class DeploymentConfigurationTests(SimpleTestCase):
    def test_postgres_database_url_is_parsed_without_third_party_configuration(self):
        config = database_from_url(
            "postgresql://nyansa:p%40ss@db.example.com:5433/nyansa_prod?sslmode=require"
        )
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "nyansa_prod")
        self.assertEqual(config["PASSWORD"], "p@ss")
        self.assertEqual(config["PORT"], "5433")
        self.assertEqual(config["OPTIONS"]["sslmode"], "require")

    def test_non_postgres_database_url_is_rejected(self):
        with self.assertRaisesMessage(RuntimeError, "postgres"):
            database_from_url("mysql://user:password@localhost/database")

    @override_settings(NYANSA_DEMO_MODE=True)
    def test_demo_mode_is_visible_on_html_pages(self):
        response = self.client.get(reverse("home"), secure=True)
        self.assertContains(response, "Demo environment")
        self.assertContains(response, "use sample data only")


class HealthEndpointTests(TestCase):
    def test_liveness_does_not_require_authentication(self):
        response = self.client.get(reverse("health_live"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness_checks_database(self):
        response = self.client.get(reverse("health_ready"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database"], "ready")

    @patch("config.views.connection.cursor", side_effect=RuntimeError("database offline"))
    def test_readiness_returns_503_when_database_is_unavailable(self, cursor):
        response = self.client.get(reverse("health_ready"), secure=True)
        self.assertEqual(response.status_code, 503)


class NavigationTests(TestCase):
    def test_school_admin_navigation_is_grouped_and_uses_membership_role(self):
        school = School.objects.create(name="Demo School", slug="demo-school")
        user = school.memberships.model._meta.get_field("user").remote_field.model.objects.create_user(
            username="admin-user", password="safe-test-password", role="TEACHER"
        )
        SchoolMembership.objects.create(
            school=school, user=user, role=SchoolMembership.Role.SCHOOL_ADMIN
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"), secure=True)

        self.assertContains(response, "Academics")
        self.assertContains(response, "School Operations")
        self.assertContains(response, "School Admin")
        self.assertContains(response, "js/navigation.js")
        self.assertContains(response, "Open School Overview")
        self.assertContains(response, "&copy; 2026 Nyansa. School intelligence")
        self.assertContains(response, "Developed by")
        self.assertContains(response, "NERDS IV Technologies")
        self.assertNotContains(response, "(Teacher)")

    def test_public_home_presents_the_school_platform_direction(self):
        response = self.client.get(reverse("home"), secure=True)

        self.assertContains(response, "School intelligence for Ghana")
        self.assertContains(response, "Academic operations")
        self.assertContains(response, "Guardian connection")
        self.assertContains(response, "Fees and payments")
        self.assertContains(response, "Responsible AI")
