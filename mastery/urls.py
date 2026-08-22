from django.urls import path
from . import views

urlpatterns = [
    path("", views.mastery_overview_view, name="mastery_overview"),
    path("goals/", views.study_goals_view, name="mastery_study_goals"),
    path("improvement-report/", views.improvement_report_view, name="mastery_improvement_report"),
    path("classes/<int:class_id>/terms/<int:term_id>/", views.class_detail_view, name="mastery_class"),
    path(
        "classes/<int:class_id>/terms/<int:term_id>/misconceptions/",
        views.misconceptions_view, name="mastery_misconceptions",
    ),
    path(
        "classes/<int:class_id>/terms/<int:term_id>/topics/<int:topic_id>/differentiate/",
        views.differentiated_tasks_view, name="mastery_differentiate",
    ),
    path("curriculum/", views.curriculum_view, name="mastery_curriculum"),
    path("offerings/<int:offering_id>/topics/", views.assign_topics_view, name="mastery_assign_topics"),
    path("quizzes/<int:quiz_id>/topics/", views.assign_question_topics_view, name="mastery_assign_question_topics"),
]
