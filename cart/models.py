# cart/models.py
from django.conf import settings
from django.db import models
from products.models import Product

class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="cart"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def get_total_price(self):
        return sum(item.get_subtotal() for item in self.items.all())

    def __str__(self):
        return f"Cart for {self.user.email}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def get_subtotal(self):
        # FIX: Respect product discounts in cart calculations
        return self.product.get_discounted_price() * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"