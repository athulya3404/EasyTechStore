from rest_framework import serializers
from .models import Order, OrderItem, Payment
from products.serializers import ProductSerializer


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True, default="Deleted Product")
    subtotal = serializers.DecimalField(source="get_subtotal", max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "price_at_purchase",
            "subtotal",
        ]
        read_only_fields = ["id", "price_at_purchase", "subtotal"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "payment_method",
            "transaction_id",
            "amount",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "transaction_id", "created_at", "updated_at"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    items_count = serializers.IntegerField(source="items.count", read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    payment = PaymentSerializer(read_only=True)
    customer_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "customer_email",
            "status",
            "recipient_name",
            "recipient_phone",
            "street_address",
            "city",
            "state",
            "postal_code",
            "shipping_address",
            "subtotal",
            "tax_amount",
            "shipping_fee",
            "total_amount",
            "expires_at",
            "items",
            "items_count",
            "payment",
            "payments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "customer_email",
            "subtotal",
            "tax_amount",
            "shipping_fee",
            "total_amount",
            "expires_at",
            "created_at",
            "updated_at",
        ]


class OrderCreateSerializer(serializers.Serializer):
    shipping_address = serializers.CharField(max_length=500, required=True)
    payment_method = serializers.ChoiceField(
        choices=["Sandbox", "COD", "Card", "UPI", "NetBanking"],
        default="Sandbox"
    )
    selected_item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list
    )


class PaymentVerificationSerializer(serializers.Serializer):
    order_id = serializers.IntegerField(required=True)
    payment_method = serializers.CharField(max_length=50, default="Sandbox")
    simulate_status = serializers.ChoiceField(
        choices=["success", "failed"],
        default="success"
    )
    transaction_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
