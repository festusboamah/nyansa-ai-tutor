from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config.settings import database_from_url


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
