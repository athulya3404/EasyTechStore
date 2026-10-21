from django.urls import path
from .views import (
    checkout_view,
    customer_orders_view,
    order_confirmation_view,
    download_invoice_view,
    payment_gateway_view,
    cancel_order_view,
    request_return_view,
    advance_order_status_view,
    resend_invoice_email_view,
)

app_name = "orders"

urlpatterns = [
    # UI Views
    path("checkout/", checkout_view, name="checkout"),
    path("payment-gateway/<int:order_id>/", payment_gateway_view, name="payment_gateway"),
    path("payment/<int:order_id>/", payment_gateway_view, name="payment"),
    path("process-payment/<int:order_id>/", payment_gateway_view, name="process_payment"),
    path("my-orders/", customer_orders_view, name="my_orders"),
    path("confirmation/<int:order_id>/", order_confirmation_view, name="confirmation"),
    path("<int:order_id>/invoice/", download_invoice_view, name="download_invoice"),
    path("<int:order_id>/invoice/pdf/", download_invoice_view, {"format_pdf": True}, name="download_invoice_pdf"),
    path("<int:order_id>/cancel/", cancel_order_view, name="cancel_order"),
    path("<int:order_id>/return/", request_return_view, name="request_return"),
    path("<int:order_id>/advance-status/", advance_order_status_view, name="advance_status"),
    path("<int:order_id>/resend-invoice/", resend_invoice_email_view, name="resend_invoice"),
]