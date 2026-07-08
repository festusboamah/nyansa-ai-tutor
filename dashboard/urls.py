from django.urls import path
from . import views

urlpatterns = [
    path("", views.teacher_dashboard_view, name="teacher_dashboard"),
    path("report/<int:student_id>/<int:subject_id>/", views.student_report_view, name="student_report"),
]