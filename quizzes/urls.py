from django.urls import path
from . import views

urlpatterns = [
    path("<int:quiz_id>/start/", views.quiz_start_view, name="quiz_start"),
    path("<int:quiz_id>/take/", views.quiz_take_view, name="quiz_take"),
    path("result/<int:submission_id>/", views.quiz_result_view, name="quiz_result"),
    path("create-choice/", views.quiz_create_choice_view, name="quiz_create_choice"),
    path("create/", views.create_quiz_view, name="create_quiz"),
    path("<int:quiz_id>/add-question/", views.add_question_view, name="add_question"),
    path("ai-generate/", views.ai_generate_quiz_view, name="ai_generate_quiz"),
    path("<int:quiz_id>/publish/", views.publish_quiz_view, name="publish_quiz"),
    path("generation-settings/", views.quiz_generation_settings_view, name="quiz_generation_settings"),
    path("bank/generate/", views.generate_bank_questions_view, name="generate_bank_questions"),
    path("bank/review/", views.bank_review_queue_view, name="bank_review_queue"),
    path("<int:quiz_id>/bank/", views.add_bank_questions_view, name="add_bank_questions"),
    path("assignments/create/", views.create_assignment_view, name="create_assignment"),
    path("assignments/<int:assignment_id>/rubric/", views.manage_rubric_view, name="manage_rubric"),
    path("assignments/<int:assignment_id>/", views.assignment_detail_view, name="assignment_detail"),
    path("assignments/<int:assignment_id>/submissions/", views.assignment_submissions_list_view, name="assignment_submissions_list"),
    path("assignments/grade/<int:submission_id>/", views.grade_assignment_view, name="grade_assignment"),
]