from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import home_view
from config.views import health_live, health_ready, service_worker_view
from integrations.views import suku360_credential_webhook_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("service-worker.js", service_worker_view, name="service_worker"),
    path("health/live/", health_live, name="health_live"),
    path("health/ready/", health_ready, name="health_ready"),
    path("", home_view, name="home"),
    path("accounts/", include("accounts.urls")),
    path("courses/", include("courses.urls")),
    path("quizzes/", include("quizzes.urls")),
    path("tutor/", include("tutor.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("schools/", include("schools.urls")),
    path("gradebook/", include("gradebook.urls")),
    path("attendance/", include("attendance.urls")),
    path("reports/", include("reports.urls")),
    path("guardian/", include("guardians.urls")),
    path("communications/", include("communications.urls")),
    path("finance/", include("finance.urls")),
    path("analytics/", include("analytics.urls")),
    path("mastery/", include("mastery.urls")),
    path("integrations/", include("integrations.urls")),
    path("ai-usage/", include("ai_core.urls")),
    path("billing/", include("billing.urls")),
    path("api/v1/", include("integrations.api_urls")),
    path("suku360/webhook/credential/", suku360_credential_webhook_view, name="suku360_credential_webhook"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
