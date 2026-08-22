from django.urls import path

from . import views

urlpatterns = [
    path("", views.ai_usage_report_view, name="ai_usage_report"),
]
