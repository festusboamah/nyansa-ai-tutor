from django.urls import path

from . import views


urlpatterns = [
    path("", views.finance_dashboard, name="finance_dashboard"),
    path("structures/new/", views.fee_structure_create, name="fee_structure_create"),
    path("structures/<int:structure_id>/", views.fee_structure_detail, name="fee_structure_detail"),
    path("students/<int:student_id>/", views.student_ledger, name="student_ledger"),
    path("students/<int:student_id>/pay/", views.start_payment, name="start_payment"),
    path("students/<int:student_id>/remind/", views.send_balance_reminder, name="send_balance_reminder"),
    path("payments/callback/", views.payment_callback, name="payment_callback"),
    path("webhooks/paystack/", views.paystack_webhook, name="paystack_webhook"),
    path("receipts/<int:receipt_id>/pdf/", views.receipt_pdf, name="receipt_pdf"),
    path("exceptions/<int:exception_id>/resolve/", views.resolve_exception_view, name="resolve_reconciliation_exception"),
]
