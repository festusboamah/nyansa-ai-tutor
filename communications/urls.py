from django.urls import path

from . import views


urlpatterns = [
    path("notifications/", views.notification_center, name="notification_center"),
    path("notifications/<int:notification_id>/read/", views.notification_read, name="notification_read"),
    path("notifications/read-all/", views.notification_mark_all_read, name="notification_mark_all_read"),
    path("preferences/", views.preferences, name="communication_preferences"),
    path("admin/", views.admin_dashboard, name="communications_dashboard"),
    path("admin/templates/new/", views.template_edit, name="message_template_create"),
    path("admin/templates/<int:template_id>/", views.template_edit, name="message_template_edit"),
    path("admin/events/new/", views.send_school_event, name="communication_school_event"),
]

