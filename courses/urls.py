from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("browse/", views.browse_subjects_view, name="browse_subjects"),
    path("enroll/<int:subject_id>/", views.enroll_view, name="enroll_subject"),
    path("subject/<int:subject_id>/", views.subject_detail_view, name="subject_detail"),
]