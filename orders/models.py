import uuid
from django.db import models
from django.conf import settings
from products.models import Product

class Order(models.Model):
    objects = models.Manager()
    # Order Checkout State Machine Constants
    STATUS_PENDING = 'Pending'
    STATUS_PAYMENT_PENDING = 'Payment_Pending'
    STATUS_PAID = 'Paid'
    STATUS_SHIPPED = 'Shipped'
    STATUS_DELIVERED = 'Delivered'
    STATUS_CANCELLED = 'Cancelled'
    STATUS_RETURN_REQUESTED = 'Return_Requested'
    STATUS_RETURNED = 'Returned'

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAYMENT_PENDING, 'Payment Pending'),
        (STATUS_PAID, 'Paid'),
        (STATUS_SHIPPED, 'Shipped'),
        (STATUS_DELIVERED, 'Delivered'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_RETURN_REQUESTED, 'Return Requested'),
        (STATUS_RETURNED, 'Returned'),
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="orders"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    
    # Structured Shipping Address Snapshot
    recipient_name = models.CharField(max_length=150, blank=True)
    recipient_phone = models.CharField(max_length=20, blank=True)
    street_address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    address = models.ForeignKey(
        'users.Address',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        help_text="Reference to user saved address"
    )
    shipping_address = models.TextField(help_text="Full shipping address string snapshot")
    
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Net order amount before taxes and shipping")
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Calculated tax (e.g. GST) for the order")
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Shipping fee charged for the order")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    expires_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text="Expiration timestamp for pending orders after which reserved stock is released"
    )

    # Delivery & Logistics Simulation
    paid_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text="Timestamp when customer payment was confirmed"
    )
    auto_delivery_days = models.PositiveSmallIntegerField(
        default=3,
        null=True,
        blank=True,
        help_text="Random delivery duration in days assigned to order"
    )
    estimated_delivery_date = models.DateField(
        null=True, 
        blank=True, 
        help_text="Estimated delivery date for the customer"
    )
    tracking_number = models.CharField(
        max_length=60, 
        blank=True, 
        help_text="Courier shipment tracking number e.g. ETX-882910"
    )
    carrier_name = models.CharField(
        max_length=100, 
        default="EasyTech Express Air", 
        help_text="Designated logistics carrier"
    )
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    invoice_sent_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text="Timestamp when the PDF tax invoice email was successfully dispatched"
    )
    return_reason = models.CharField(max_length=255, blank=True, null=True, help_text="Customer reason for return/replacement")
    return_requested_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when return was initiated")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def get_total_price(self):
        if self.total_amount and self.total_amount > 0:
            return self.total_amount
        return sum(item.get_subtotal() for item in self.items.all())

    @property
    def delivery_days_left(self):
        """Calculates days remaining until estimated delivery."""
        if self.status == self.STATUS_DELIVERED:
            return 0
        if self.status == self.STATUS_CANCELLED or not self.estimated_delivery_date:
            return None
        from django.utils import timezone
        diff = (self.estimated_delivery_date - timezone.now().date()).days
        return max(0, diff)

    @property
    def delivery_status_display(self):
        """Human-readable delivery timeline description formatted in Amazon/Flipkart style."""
        if self.status == self.STATUS_DELIVERED:
            deliv_date = self.delivered_at.strftime('%A, %b %d') if self.delivered_at else (self.estimated_delivery_date.strftime('%A, %b %d') if self.estimated_delivery_date else 'Recently')
            return f"Delivered on {deliv_date} • Package handed to resident"
        if self.status == self.STATUS_CANCELLED:
            return "Order Cancelled"
        if not self.estimated_delivery_date:
            if self.status == self.STATUS_SHIPPED:
                return "In Transit via Express Courier (2–4 business days)"
            elif self.status == self.STATUS_PAID:
                return "Payment Confirmed • Preparing for dispatch"
            return "Delivery date will be assigned once payment is confirmed"

        days = self.delivery_days_left
        date_str = self.estimated_delivery_date.strftime('%A, %b %d')
        if self.status == self.STATUS_PAID:
            days_str = f" • {days} days left" if days is not None and days > 0 else ""
            return f"Preparing for Dispatch • Estimated by {date_str}{days_str}"
        if days == 0:
            return f"Arriving Today by 9:00 PM ({date_str})"
        elif days == 1:
            return f"Arriving Tomorrow ({date_str}) • 1 day left"
        else:
            return f"Arriving by {date_str} • {days} days left"

    @property
    def payment(self):
        """Returns the most recent payment attempt for backward compatibility."""
        return self.payments.order_by("-created_at").first()

    def __str__(self):
        return f"Order #{self.id} - {self.user.email} ({self.status})"

class OrderItem(models.Model):
    objects = models.Manager()
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField(default=1)
    
    # Store price at purchase so historical orders don't change if product prices are updated
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2) 

    def get_subtotal(self):
        return self.price_at_purchase * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product.name if self.product else 'Deleted Product'}"


class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = (
        ('Sandbox', 'Sandbox / Mock Instant Payment'),
        ('COD', 'Cash On Delivery'),
        ('Razorpay', 'Razorpay'),
        ('Stripe', 'Stripe'),
    )
    PAYMENT_STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Success', 'Success'),
        ('Failed', 'Failed'),
        ('Refunded', 'Refunded'),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='Sandbox')
    transaction_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment for Order #{self.order_id} - TXN: {self.transaction_id} ({self.status})"

    @property
    def payment_status(self):
        return self.status


