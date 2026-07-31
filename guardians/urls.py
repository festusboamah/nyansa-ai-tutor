from django.urls import path

from . import views


urlpatterns = [
    path("", views.portal, name="guardian_portal"),
    path("students/<int:student_id>/", views.student_detail, name="guardian_student_detail"),
    path("reports/<int:report_id>/pdf/", views.published_report_pdf, name="guardian_report_pdf"),
    path("manage/links/", views.manage_links, name="guardian_links"),
    path("manage/links/<int:link_id>/revoke/", views.revoke_link_view, name="guardian_link_revoke"),
]

