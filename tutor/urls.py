from django.urls import path
from . import views

urlpatterns = [
    path("", views.tutor_home_view, name="tutor_home"),
    path("start/", views.start_session_view, name="tutor_start_session"),
    path("<int:session_id>/", views.session_detail_view, name="tutor_session_detail"),
    path("settings/", views.tutor_settings_view, name="tutor_settings"),
]
