from django.urls import path
from . import views

urlpatterns = [
    path("", views.teacher_dashboard_view, name="teacher_dashboard"),
    path("report/<int:student_id>/<int:subject_id>/", views.student_report_view, name="student_report"),
    path("lesson-notes/", views.lesson_notes_list_view, name="lesson_notes_list"),
    path("lesson-notes/create/", views.create_lesson_note_view, name="create_lesson_note"),
    path("lesson-notes/<int:note_id>/", views.lesson_note_detail_view, name="lesson_note_detail"),
    path("lesson-notes/<int:note_id>/edit/", views.edit_lesson_note_view, name="edit_lesson_note"),
    path("lesson-notes/<int:note_id>/submit/", views.submit_lesson_note_view, name="submit_lesson_note"),
    path("lesson-notes/<int:note_id>/comment/", views.comment_lesson_note_view, name="comment_lesson_note"),
    path("lesson-notes/<int:note_id>/download/", views.download_lesson_note_pdf, name="download_lesson_note"),
    path("lesson-review/", views.lesson_review_queue_view, name="lesson_review_queue"),
    path("lesson-review/<int:note_id>/", views.lesson_review_detail_view, name="lesson_review_detail"),
    path("lesson-review/<int:note_id>/decision/", views.review_lesson_note_view, name="review_lesson_note"),
    path("notifications/", views.lesson_notifications_view, name="lesson_notifications"),
    path("notifications/<int:notification_id>/read/", views.read_lesson_notification_view, name="read_lesson_notification"),
    path("report/<int:student_id>/<int:subject_id>/email/", views.email_student_report_view, name="email_student_report"),
]
