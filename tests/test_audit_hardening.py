from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient
from rest_framework import status

from products.models import Product, Category, Brand
from cart.models import Cart, CartItem
from orders.models import Order, OrderItem, Payment

User = get_user_model()


class AuditHardeningTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="audit@example.com",
            password="StrongPassword123!",
            name="Audit Customer",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(name="Audio", slug="audio", is_active=True)
        self.brand = Brand.objects.create(name="Sony", description="Sony Audio")
        self.product = Product.objects.create(
            name="Sony WH-1000XM5",
            slug="sony-wh-1000xm5",
            category=self.category,
            brand=self.brand,
            price=Decimal("29990.00"),
            stock=10,
            is_active=True,
        )

        self.cart = Cart.objects.create(user=self.user)
        self.cart_item = CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            quantity=1,
        )

    def test_order_financial_breakdown_on_creation(self):
        """Verify that subtotal, tax_amount (18% GST), and shipping_fee are populated."""
        response = self.client.post("/api/orders/place_order/", {
            "shipping_address": "456 Tech Boulevard, Bangalore, Karnataka, 560001",
            "recipient_name": "Audit Tester",
            "recipient_phone": "9876543210",
            "payment_method": "Sandbox",
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(id=response.data["order_id"])

        self.assertGreater(order.total_amount, 0)
        self.assertGreater(order.subtotal, 0)
        self.assertGreater(order.tax_amount, 0)
        self.assertEqual(order.shipping_fee, Decimal("0.00"))
        # Verify subtotal + tax_amount approximates total_amount
        self.assertAlmostEqual(float(order.subtotal + order.tax_amount), float(order.total_amount), places=1)

    def test_payment_idempotency(self):
        """Verify that duplicate payment verification requests return idempotent response without duplicating payments."""
        # Create pending order
        create_resp = self.client.post("/api/orders/place_order/", {
            "shipping_address": "456 Tech Boulevard, Bangalore",
            "recipient_name": "Audit Tester",
            "payment_method": "Card",
        }, format="json")
        order_id = create_resp.data["order_id"]

        idempotency_key = "IDEMP-TEST-KEY-12345"

        # First verification request
        resp1 = self.client.post("/api/payments/verify/", {
            "order_id": order_id,
            "payment_method": "Card",
            "simulate_status": "success",
            "idempotency_key": idempotency_key,
        }, format="json")

        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        self.assertTrue(resp1.data["success"])

        order = Order.objects.get(id=order_id)
        self.assertEqual(order.status, Order.STATUS_PAID)
        self.assertEqual(order.payments.filter(status="Success").count(), 1)

        # Second verification request with identical parameters (simulating double click)
        resp2 = self.client.post("/api/payments/verify/", {
            "order_id": order_id,
            "payment_method": "Card",
            "simulate_status": "success",
            "idempotency_key": idempotency_key,
        }, format="json")

        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertTrue(resp2.data.get("idempotent", False))
        # Ensure duplicate Payment record was NOT created
        self.assertEqual(order.payments.filter(status="Success").count(), 1)

    def test_pdf_invoice_endpoint(self):
        """Verify that /orders/<id>/invoice/pdf/ returns a valid PDF binary response."""
        order = Order.objects.create(
            user=self.user,
            recipient_name="Audit Tester",
            recipient_phone="9876543210",
            street_address="456 Tech Blvd",
            city="Bangalore",
            state="Karnataka",
            postal_code="560001",
            shipping_address="456 Tech Blvd, Bangalore",
            status=Order.STATUS_PAID,
            subtotal=Decimal("25415.25"),
            tax_amount=Decimal("4574.75"),
            shipping_fee=Decimal("0.00"),
            total_amount=Decimal("29990.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            price_at_purchase=Decimal("29990.00"),
        )

        self.client.force_login(self.user)
        # Use django test client for UI view
        response = self.client.get(f"/orders/{order.id}/invoice/pdf/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_run_order_worker_once(self):
        """Verify that run_order_worker management command executes cleanly with --once."""
        call_command("run_order_worker", interval=1, once=True)
