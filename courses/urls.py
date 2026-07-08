from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("browse/", views.browse_subjects_view, name="browse_subjects"),
    path("enroll/<int:subject_id>/", views.enroll_view, name="enroll_subject"),
    path("subject/<int:subject_id>/", views.subject_detail_view, name="subject_detail"),
    path("create-subject/", views.create_subject_view, name="create_subject"),
    path("create-material/", views.create_material_view, name="create_material"),
    path("study/", views.study_documents_view, name="study_documents"),
    path("study/upload/", views.upload_study_document_view, name="upload_study_document"),
    path("study/<int:document_id>/", views.study_document_detail_view, name="study_document_detail"),
    path("unenroll/<int:subject_id>/", views.unenroll_view, name="unenroll_subject"),
    path("transcript/", views.transcript_view, name="transcript"),
    path("transcript/download/", views.download_transcript_pdf, name="download_transcript"),
]