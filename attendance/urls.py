from django.urls import path

from . import views


urlpatterns = [
    path("", views.attendance_dashboard, name="attendance_dashboard"),
    path("classes/<int:class_id>/terms/<int:term_id>/", views.class_attendance_summary, name="class_attendance_summary"),
    path("classes/<int:class_id>/terms/<int:term_id>/export.csv", views.attendance_summary_csv, name="attendance_summary_csv"),
    path("classes/<int:class_id>/terms/<int:term_id>/register/", views.attendance_register, name="attendance_register"),
    path("records/<int:record_id>/correct/", views.correct_attendance_view, name="attendance_correct"),
    path("calendar/", views.calendar_settings, name="attendance_calendar"),
    path("calendar/closures/add/", views.add_closure, name="attendance_add_closure"),
]
