from django.urls import path

from . import views


urlpatterns = [
    path("preferences/", views.preferences, name="communication_preferences"),
    path("admin/", views.admin_dashboard, name="communications_dashboard"),
    path("admin/templates/new/", views.template_edit, name="message_template_create"),
    path("admin/templates/<int:template_id>/", views.template_edit, name="message_template_edit"),
    path("admin/events/new/", views.send_school_event, name="communication_school_event"),
]

