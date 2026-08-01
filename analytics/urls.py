from django.urls import path

from . import views


urlpatterns = [
    path("", views.dashboard, name="analytics_dashboard"),
    path("classes/<int:class_id>/terms/<int:term_id>/", views.class_detail, name="analytics_class"),
    path("offerings/<int:offering_id>/", views.offering_detail, name="analytics_offering"),
    path("policies/", views.policies, name="analytics_policies"),
    path("signals/<int:signal_id>/", views.signal_detail, name="analytics_signal"),
    path("narratives/<int:narrative_id>/approve/", views.approve_narrative_view, name="analytics_narrative_approve"),
]

