from django.urls import path

from . import views

urlpatterns = [
    path("", views.billing_dashboard_view, name="billing_dashboard"),
    path("plans/", views.plans_view, name="billing_plans"),
    path("invoices/<int:invoice_id>/pay/", views.pay_invoice_view, name="billing_pay_invoice"),
    path("payment/callback/", views.payment_callback_view, name="billing_payment_callback"),
    path("webhook/paystack/", views.paystack_webhook_view, name="billing_paystack_webhook"),
]
