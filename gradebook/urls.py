from django.urls import path

from . import views


urlpatterns = [
    path("", views.offering_list, name="gradebook_offerings"),
    path("offerings/<int:offering_id>/", views.assessment_list, name="gradebook_assessments"),
    path("offerings/<int:offering_id>/assessments/new/", views.create_assessment, name="gradebook_create_assessment"),
    path("assessments/<int:assessment_id>/roster/", views.grade_roster, name="gradebook_roster"),
]
