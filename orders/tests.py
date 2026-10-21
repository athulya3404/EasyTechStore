from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import resolve
from rest_framework import status
from rest_framework.test import APITestCase

from category.models import Category
from products.models import Product
from cart.models import Cart, CartItem
from orders.models import Order, OrderItem, Payment
from orders.views import OrderViewSet

User = get_user_model()


class OrderAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com",
            password="testpassword123",
        )
        self.category = Category.objects.create(name="Electronics")
        self.product = Product.objects.create(
            name="Laptop",
            price=Decimal("999.99"),
            stock=10,
            category=self.category,
        )
        self.client.force_authenticate(user=self.user)

    def test_order_urls_resolve(self):
        match = resolve("/api/orders/place_order/")
        self.assertEqual(match.func.cls, OrderViewSet)
        self.assertEqual(match.func.actions["post"], "place_order")

    def test_place_order_success(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)

        response = self.client.post(
            "/api/orders/place_order/",
            {"shipping_address": "123 Tech Lane, Silicon Valley, CA 94025"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("order_id", response.data)

        # Cart items should be cleared
        self.assertEqual(cart.items.count(), 0)

        # Order and OrderItem should exist
        order = Order.objects.get(id=response.data["order_id"])
        self.assertEqual(order.user, self.user)
        self.assertEqual(order.shipping_address, "123 Tech Lane, Silicon Valley, CA 94025")
        self.assertEqual(order.items.count(), 1)
        order_item = order.items.first()
        self.assertEqual(order_item.product, self.product)
        self.assertEqual(order_item.quantity, 2)
        self.assertEqual(order_item.price_at_purchase, Decimal("999.99"))

    def test_place_order_empty_cart(self):
        response = self.client.post(
            "/api/orders/place_order/",
            {"shipping_address": "123 Tech Lane"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Your cart is empty.")

    def test_place_order_missing_shipping_address(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)

        response = self.client.post(
            "/api/orders/place_order/",
            {"shipping_address": ""},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Shipping address is required.")

    def test_cancel_order_restores_stock_and_redirects_to_cancelled_tab(self):
        self.product.stock = 8
        self.product.save()

        order = Order.objects.create(
            user=self.user,
            shipping_address="123 Tech Lane",
            status=Order.STATUS_PENDING,
            total_amount=Decimal("1999.98"),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            price_at_purchase=Decimal("999.99"),
        )
        payment = Payment.objects.create(
            order=order,
            payment_method="Sandbox",
            transaction_id="TXN-TEST-123",
            amount=Decimal("1999.98"),
            status="Pending",
        )

        self.client.force_login(self.user)
        response = self.client.post(f"/orders/{order.id}/cancel/")
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response.url, "/orders/my-orders/?status=Cancelled")

        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELLED)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

        payment.refresh_from_db()
        self.assertEqual(payment.status, "Failed")

    def test_customer_orders_view_filtering_cancelled(self):
        order_cancelled = Order.objects.create(
            user=self.user,
            shipping_address="123 Tech Lane",
            status=Order.STATUS_CANCELLED,
            total_amount=Decimal("100.00"),
        )
        order_paid = Order.objects.create(
            user=self.user,
            shipping_address="123 Tech Lane",
            status=Order.STATUS_PAID,
            total_amount=Decimal("200.00"),
        )

        self.client.force_login(self.user)
        response = self.client.get("/orders/my-orders/?status=Cancelled")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.context["orders"]), 1)
        self.assertEqual(response.context["orders"][0].id, order_cancelled.id)
        self.assertEqual(response.context["selected_status"], "Cancelled")
        self.assertEqual(response.context["cancelled_count"], 1)
        self.assertEqual(response.context["paid_count"], 1)

    def test_expired_pending_order_is_deleted_after_10_minutes(self):
        self.product.stock = 8
        self.product.save()

        past_expiration = timezone.now() - timedelta(minutes=1)
        expired_order = Order.objects.create(
            user=self.user,
            shipping_address="123 Tech Lane",
            status=Order.STATUS_PENDING,
            total_amount=Decimal("1999.98"),
            expires_at=past_expiration,
        )
        OrderItem.objects.create(
            order=expired_order,
            product=self.product,
            quantity=2,
            price_at_purchase=Decimal("999.99"),
        )

        self.client.force_login(self.user)
        response = self.client.get(f"/orders/payment-gateway/{expired_order.id}/")
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response.url, "/cart/")

        # Order must be deleted from DB, NOT cancelled
        self.assertFalse(Order.objects.filter(id=expired_order.id).exists())

        # Stock must be restored to 10
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

