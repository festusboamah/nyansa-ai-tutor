from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class NyansaAdminUITests(TestCase):
    def test_admin_login_uses_nyansa_branding_and_styles(self):
        response = self.client.get(reverse("admin:login"), secure=True)

        self.assertContains(response, "Nyansa")
        self.assertContains(response, "System administration")
        self.assertContains(response, "admin/css/nyansa-admin.css")
        self.assertContains(response, "images/favicon-32.png")

    def test_superadmin_dashboard_uses_control_room_layout(self):
        user = get_user_model().objects.create_superuser(
            username="admin-ui-test",
            email="admin-ui@example.com",
            password="safe-test-password",
            first_name="Ama",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:index"), secure=True)

        self.assertContains(response, "Welcome back, Ama")
        self.assertContains(response, "Choose where to work")
        self.assertContains(response, "Your recent actions")
        self.assertContains(response, "View public site")
