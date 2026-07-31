from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import home_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home_view, name="home"),
    path("accounts/", include("accounts.urls")),
    path("courses/", include("courses.urls")),
    path("quizzes/", include("quizzes.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("schools/", include("schools.urls")),
    path("gradebook/", include("gradebook.urls")),
    path("attendance/", include("attendance.urls")),
    path("reports/", include("reports.urls")),
    path("guardian/", include("guardians.urls")),
    path("communications/", include("communications.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
