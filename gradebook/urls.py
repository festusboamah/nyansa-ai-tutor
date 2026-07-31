from django.urls import path

from . import views


urlpatterns = [
    path("", views.offering_list, name="gradebook_offerings"),
    path("offerings/<int:offering_id>/", views.assessment_list, name="gradebook_assessments"),
    path("offerings/<int:offering_id>/assessments/new/", views.create_assessment, name="gradebook_create_assessment"),
    path("assessments/<int:assessment_id>/roster/", views.grade_roster, name="gradebook_roster"),
    path("assessments/<int:assessment_id>/template/", views.download_grade_template, name="gradebook_template"),
    path("assessments/<int:assessment_id>/import/", views.upload_grade_workbook, name="gradebook_import"),
    path("assessments/<int:assessment_id>/sync/", views.sync_assessment, name="gradebook_sync"),
    path("entries/<int:entry_id>/correct/", views.correct_grade, name="gradebook_correct"),
    path("imports/<int:batch_id>/", views.import_preview, name="gradebook_import_preview"),
    path("imports/<int:batch_id>/confirm/", views.confirm_import, name="gradebook_import_confirm"),
    path("review/", views.grade_review_queue, name="gradebook_review_queue"),
    path("review/<int:entry_id>/", views.review_grade, name="gradebook_review"),
]
