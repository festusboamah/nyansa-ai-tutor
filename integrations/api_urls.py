from django.urls import path
from . import views

urlpatterns = [
    path("evidence/", views.evidence_view, name="api_evidence"),
    path("mastery-summary/", views.mastery_summary_view, name="api_mastery_summary"),
    path("risk-signals/", views.risk_signals_view, name="api_risk_signals"),
]
