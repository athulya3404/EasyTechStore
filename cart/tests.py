from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import resolve
from rest_framework import status
from rest_framework.test import APITestCase

from category.models import Category
from products.models import Product
from cart.models import Cart, CartItem
from cart.views import CartViewSet

User = get_user_model()


class CartAPITests(APITestCase):
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

    def test_cart_urls_resolve(self):
        match = resolve("/api/cart/add_item/")
        self.assertEqual(match.func.cls, CartViewSet)
        self.assertEqual(match.func.actions["post"], "add_item")

        match_update = resolve("/api/cart/update_quantity/1/")
        self.assertEqual(match_update.func.cls, CartViewSet)
        self.assertEqual(match_update.func.actions["patch"], "update_quantity")

        match_remove = resolve("/api/cart/remove_item/1/")
        self.assertEqual(match_remove.func.cls, CartViewSet)
        self.assertEqual(match_remove.func.actions["delete"], "remove_item")

    def test_add_item_to_cart(self):
        response = self.client.post(
            "/api/cart/add_item/",
            {"product_id": self.product.id, "quantity": 2},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cart = Cart.objects.get(user=self.user)
        self.assertEqual(cart.items.count(), 1)
        item = cart.items.first()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.quantity, 2)

    def test_add_item_invalid_quantity(self):
        response = self.client.post(
            "/api/cart/add_item/",
            {"product_id": self.product.id, "quantity": 0},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Quantity must be greater than 0.")

    def test_add_item_exceeds_stock(self):
        response = self.client.post(
            "/api/cart/add_item/",
            {"product_id": self.product.id, "quantity": 15},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("left in stock", response.data["error"])

    def test_update_cart_item_quantity(self):
        cart = Cart.objects.create(user=self.user)
        cart_item = CartItem.objects.create(cart=cart, product=self.product, quantity=1)

        response = self.client.patch(
            f"/api/cart/update_quantity/{cart_item.id}/",
            {"quantity": 5},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cart_item.refresh_from_db()
        self.assertEqual(cart_item.quantity, 5)

    def test_remove_cart_item(self):
        cart = Cart.objects.create(user=self.user)
        cart_item = CartItem.objects.create(cart=cart, product=self.product, quantity=1)

        response = self.client.delete(f"/api/cart/remove_item/{cart_item.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(CartItem.objects.filter(id=cart_item.id).exists())
