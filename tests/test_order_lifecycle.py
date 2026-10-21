from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.test import TestCase

from orders.models import Order, OrderItem, Payment
from products.models import Product
from category.models import Category
from orders.services_lifecycle import (
    advance_paid_to_shipped,
    advance_shipped_to_delivered,
    run_order_progression_sweep,
    calculate_random_delivery_days
)

User = get_user_model()


class OrderLifecycleTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="shopper@example.com",
            password="Password123!",
            name="Test Customer"
        )
        self.category = Category.objects.create(name="Laptops")
        self.product = Product.objects.create(
            name="Ultrabook Pro 15",
            category=self.category,
            price=75000,
            stock=10
        )

    def test_calculate_random_delivery_days(self):
        order = Order.objects.create(
            user=self.user,
            status=Order.STATUS_PAID,
            total_amount=75000
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            price_at_purchase=75000
        )
        days = calculate_random_delivery_days(order)
        self.assertGreaterEqual(days, 2)
        self.assertLessEqual(days, 5)

    def test_paid_to_shipped_timing(self):
        now = timezone.now()
        
        # Order 1: Paid 70 minutes ago -> SHOULD advance
        order_mature = Order.objects.create(
            user=self.user,
            status=Order.STATUS_PAID,
            paid_at=now - timedelta(minutes=70),
            total_amount=75000
        )
        
        # Order 2: Paid 20 minutes ago -> SHOULD NOT advance
        order_fresh = Order.objects.create(
            user=self.user,
            status=Order.STATUS_PAID,
            paid_at=now - timedelta(minutes=20),
            total_amount=75000
        )

        shipped_orders = advance_paid_to_shipped(hours_delay=1, immediate=False)
        self.assertIn(order_mature, shipped_orders)
        self.assertNotIn(order_fresh, shipped_orders)

        order_mature.refresh_from_db()
        order_fresh.refresh_from_db()

        self.assertEqual(order_mature.status, Order.STATUS_SHIPPED)
        self.assertIsNotNone(order_mature.shipped_at)
        self.assertTrue(order_mature.tracking_number.startswith("ETX-"))
        self.assertIsNotNone(order_mature.estimated_delivery_date)

        self.assertEqual(order_fresh.status, Order.STATUS_PAID)

    def test_shipped_to_delivered_timing(self):
        now = timezone.now()

        # Order 1: Shipped, delivery date was yesterday -> SHOULD advance to Delivered
        order_due = Order.objects.create(
            user=self.user,
            status=Order.STATUS_SHIPPED,
            shipped_at=now - timedelta(days=4),
            auto_delivery_days=3,
            estimated_delivery_date=(now - timedelta(days=1)).date(),
            total_amount=75000
        )

        # Order 2: Shipped, delivery date is 3 days in future -> SHOULD NOT advance
        order_future = Order.objects.create(
            user=self.user,
            status=Order.STATUS_SHIPPED,
            shipped_at=now,
            auto_delivery_days=4,
            estimated_delivery_date=(now + timedelta(days=3)).date(),
            total_amount=75000
        )

        delivered = advance_shipped_to_delivered(immediate=False)
        self.assertIn(order_due, delivered)
        self.assertNotIn(order_future, delivered)

        order_due.refresh_from_db()
        order_future.refresh_from_db()

        self.assertEqual(order_due.status, Order.STATUS_DELIVERED)
        self.assertIsNotNone(order_due.delivered_at)
        self.assertEqual(order_future.status, Order.STATUS_SHIPPED)

    def test_immediate_demo_mode(self):
        now = timezone.now()
        order = Order.objects.create(
            user=self.user,
            status=Order.STATUS_PAID,
            paid_at=now,  # Just paid seconds ago
            total_amount=75000
        )
        
        # Advance with immediate=True
        res = run_order_progression_sweep(hours_delay=1, immediate=True)
        order.refresh_from_db()
        
        # When immediate=True, Paid -> Shipped and Shipped -> Delivered in 1 sweep
        self.assertEqual(order.status, Order.STATUS_DELIVERED)
        self.assertIsNotNone(order.shipped_at)
        self.assertIsNotNone(order.delivered_at)
