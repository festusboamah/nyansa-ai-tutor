from django.urls import path
from . import views

urlpatterns = [
    path("", views.teacher_dashboard_view, name="teacher_dashboard"),
    path("report/<int:student_id>/<int:subject_id>/", views.student_report_view, name="student_report"),
    path("lesson-notes/", views.lesson_notes_list_view, name="lesson_notes_list"),
    path("lesson-notes/create/", views.create_lesson_note_view, name="create_lesson_note"),
    path("lesson-notes/<int:note_id>/", views.lesson_note_detail_view, name="lesson_note_detail"),
    path("lesson-notes/<int:note_id>/download/", views.download_lesson_note_pdf, name="download_lesson_note"),
]