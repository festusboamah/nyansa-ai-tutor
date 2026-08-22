from django.urls import path
from . import views

urlpatterns = [
    path("credential/", views.credential_settings_view, name="integration_credential_settings"),
]
