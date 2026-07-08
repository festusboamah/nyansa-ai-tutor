from django.urls import path
from . import views

urlpatterns = [
    path("<int:quiz_id>/start/", views.quiz_start_view, name="quiz_start"),
    path("<int:quiz_id>/take/", views.quiz_take_view, name="quiz_take"),
    path("result/<int:submission_id>/", views.quiz_result_view, name="quiz_result"),
]