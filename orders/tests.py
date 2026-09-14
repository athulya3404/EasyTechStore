from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import resolve
from rest_framework import status
from rest_framework.test import APITestCase

from category.models import Category
from products.models import Product
from cart.models import Cart, CartItem
from orders.models import Order, OrderItem
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
