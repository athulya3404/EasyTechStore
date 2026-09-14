from rest_framework import serializers
from .models import Product, ProductImage


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "created_at"]


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )
    brand_name = serializers.CharField(
        source="brand.name",
        read_only=True,
        default="",
    )
    discounted_price = serializers.DecimalField(
        source="get_discounted_price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    stock_status = serializers.CharField(
        read_only=True,
    )
    average_rating = serializers.FloatField(
        read_only=True,
    )
    review_count = serializers.IntegerField(
        read_only=True,
    )
    gallery_images = ProductImageSerializer(many=True, read_only=True)
    
    # Explicitly define is_active so it defaults to True when creating via API
    is_active = serializers.BooleanField(default=True, required=False)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "specifications",
            "price",
            "discount",
            "discounted_price",
            "stock",
            "stock_status",
            "category",
            "category_name",
            "brand",
            "brand_name",
            "image",
            "gallery_images",
            "average_rating",
            "review_count",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "discounted_price",
            "stock_status",
            "average_rating",
            "review_count",
            "created_at",
            "updated_at",
        ]