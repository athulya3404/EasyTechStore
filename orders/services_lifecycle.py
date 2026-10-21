import random
import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from orders.models import Order

logger = logging.getLogger(__name__)

CARRIERS = [
    "EasyTech Express Air",
    "BlueDart Logistics",
    "Delhivery Express",
    "DTDC Air Cargo",
    "Shadowfax Prime",
]


def calculate_random_delivery_days(order):
    """
    Calculates random delivery duration (in days) based on products in the order.
    Returns integer number of days (2 to 5 days).
    """
    categories = []
    try:
        for item in order.items.select_related("product__category").all():
            if item.product and item.product.category:
                categories.append(item.product.category.name.lower())
    except Exception:
        pass

    cat_str = " ".join(categories)
    if "laptop" in cat_str or "computer" in cat_str:
        return random.randint(3, 5)
    elif "smartphone" in cat_str or "mobile" in cat_str or "phone" in cat_str:
        return random.randint(2, 4)
    elif "accessories" in cat_str or "audio" in cat_str or "headphone" in cat_str:
        return random.randint(2, 3)
    else:
        return random.randint(2, 5)


def advance_paid_to_shipped(hours_delay=1, immediate=False):
    """
    Advances orders from Paid -> Shipped after hours_delay (default: 1 hour) has elapsed
    since payment was confirmed.
    """
    now = timezone.now()
    paid_orders = Order.objects.filter(status=Order.STATUS_PAID)

    if not immediate:
        cutoff = now - timedelta(hours=hours_delay)
        paid_orders = paid_orders.filter(
            Q(paid_at__lte=cutoff) | Q(paid_at__isnull=True, created_at__lte=cutoff)
        )

    shipped_orders_list = []
    for order in paid_orders:
        order.status = Order.STATUS_SHIPPED
        order.shipped_at = now

        if not order.tracking_number:
            order.tracking_number = f"ETX-{random.randint(100000, 999999)}"

        if not order.carrier_name or order.carrier_name == "EasyTech Express Air":
            order.carrier_name = random.choice(CARRIERS)

        if not order.auto_delivery_days or order.auto_delivery_days == 3:
            order.auto_delivery_days = calculate_random_delivery_days(order)

        if not order.estimated_delivery_date:
            order.estimated_delivery_date = (now + timedelta(days=order.auto_delivery_days)).date()

        order.save(update_fields=[
            "status",
            "shipped_at",
            "tracking_number",
            "carrier_name",
            "auto_delivery_days",
            "estimated_delivery_date",
            "updated_at"
        ])
        shipped_orders_list.append(order)
        logger.info("Auto-shipped Order #%d (Tracking: %s, Carrier: %s, Est. Delivery: %s)",
                    order.id, order.tracking_number, order.carrier_name, order.estimated_delivery_date)

    return shipped_orders_list


def advance_shipped_to_delivered(immediate=False):
    """
    Advances orders from Shipped -> Delivered when the assigned random delivery
    window has elapsed.
    """
    now = timezone.now()
    today = now.date()
    shipped_orders = Order.objects.filter(status=Order.STATUS_SHIPPED)

    if not immediate:
        eligible_pks = []
        for o in shipped_orders:
            is_due = False
            if o.estimated_delivery_date and o.estimated_delivery_date <= today:
                is_due = True
            elif o.shipped_at and o.auto_delivery_days:
                if o.shipped_at + timedelta(days=o.auto_delivery_days) <= now:
                    is_due = True
            if is_due:
                eligible_pks.append(o.id)
        shipped_orders = shipped_orders.filter(id__in=eligible_pks)

    delivered_orders_list = []
    for order in shipped_orders:
        order.status = Order.STATUS_DELIVERED
        order.delivered_at = now
        order.save(update_fields=["status", "delivered_at", "updated_at"])
        delivered_orders_list.append(order)
        logger.info("Auto-delivered Order #%d (Delivered at: %s)", order.id, order.delivered_at)

    return delivered_orders_list


def cleanup_expired_unpaid_orders():
    """
    Deletes orders that have exceeded the 10-minute checkout window without payment.
    Restores reserved inventory back to product stock before deletion.
    """
    from django.db import transaction
    from django.db.models import F
    from products.models import Product

    now = timezone.now()
    # Check pending orders whose expires_at is past, or created > 10 mins ago if expires_at was null
    expired_orders = Order.objects.filter(
        status__in=[Order.STATUS_PENDING, Order.STATUS_PAYMENT_PENDING]
    ).filter(
        Q(expires_at__lte=now) | Q(expires_at__isnull=True, created_at__lte=now - timedelta(minutes=10))
    ).prefetch_related('items__product').distinct()

    deleted_count = 0
    for order in expired_orders:
        try:
            with transaction.atomic():
                for item in order.items.all():
                    if item.product_id:
                        Product.objects.filter(id=item.product_id).update(stock=F('stock') + item.quantity)
                order_id = order.id
                order.delete()
                deleted_count += 1
                logger.info("Auto-deleted unpaid expired Order #%d after 10-minute window", order_id)
        except Exception as e:
            logger.error("Error deleting expired unpaid order #%d: %s", order.id, e)
    return deleted_count


def run_order_progression_sweep(hours_delay=1, immediate=False):
    """
    Executes a complete lifecycle progression pass:
    1. Deletes unpaid orders exceeding the 10-minute window and restores inventory.
    2. Advances Paid orders to Shipped.
    3. Advances Shipped orders to Delivered.
    """
    deleted_unpaid = cleanup_expired_unpaid_orders()
    shipped = advance_paid_to_shipped(hours_delay=hours_delay, immediate=immediate)
    delivered = advance_shipped_to_delivered(immediate=immediate)
    return {
        "deleted_unpaid_count": deleted_unpaid,
        "shipped_count": len(shipped),
        "delivered_count": len(delivered),
        "shipped_orders": [o.id for o in shipped],
        "delivered_orders": [o.id for o in delivered],
    }
