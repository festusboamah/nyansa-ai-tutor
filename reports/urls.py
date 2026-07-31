from django.urls import path

from . import views


urlpatterns = [
    path("", views.report_dashboard, name="term_report_dashboard"),
    path("classes/<int:class_id>/terms/<int:term_id>/", views.class_reports, name="class_term_reports"),
    path("classes/<int:class_id>/terms/<int:term_id>/download/", views.class_reports_zip, name="class_term_reports_zip"),
    path("<int:report_id>/", views.report_detail, name="term_report_detail"),
    path("<int:report_id>/pdf/", views.report_pdf, name="term_report_pdf"),
    path("policy/<int:year_id>/", views.report_policy, name="term_report_policy"),
]

