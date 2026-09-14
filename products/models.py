from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from category.models import Category


class Brand(models.Model):
    objects = models.Manager()
    name = models.CharField(max_length=100, unique=True)
    categories = models.ManyToManyField(
        Category,
        blank=True,
        related_name="brands",
        help_text="Categories associated with this brand (e.g. Laptops, Smartphones)"
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    objects = models.Manager()
    name = models.CharField(max_length=200)

    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True
    )

    description = models.TextField(blank=True)

    specifications = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured technical specifications (e.g. {'RAM': '16GB', 'Processor': 'Intel i7'})"
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    discount = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Discount percentage (0-100)"
    )

    stock = models.PositiveIntegerField(default=0)

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )

    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )

    image = models.ImageField(
        upload_to="products/",
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Auto-convert raw string or key-value specifications into structured dictionary
        if isinstance(self.specifications, str):
            import json
            raw = self.specifications.strip()
            if not raw:
                self.specifications = {}
            else:
                try:
                    data = json.loads(raw)
                    self.specifications = data if isinstance(data, dict) else {}
                except Exception:
                    parsed = {}
                    import re
                    delimiters = r'[;\r\n]+' if (';' in raw or '\n' in raw) else r',|[\r\n]+'
                    for line in re.split(delimiters, raw):
                        line = line.strip()
                        if not line:
                            continue
                        if ":" in line:
                            k, v = line.split(":", 1)
                            if k.strip():
                                parsed[k.strip()] = v.strip()
                        else:
                            parsed[line] = ""
                    self.specifications = parsed

        if not self.slug:
            base_slug = slugify(self.name) or "product"
            slug = base_slug
            counter = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


    def get_absolute_url(self):
        if self.slug:
            return reverse("product_detail", kwargs={"slug": self.slug})
        return reverse("product_detail", kwargs={"pk": self.pk})

    def get_discounted_price(self):
        if self.discount and self.discount > 0:
            discount_amount = (self.price * self.discount) / 100
            return self.price - discount_amount
        return self.price

    @property
    def stock_status(self):
        if self.stock > 10:
            return "In Stock"
        elif self.stock > 0:
            return "Low Stock"
        return "Out of Stock"

    @property
    def average_rating(self):
        avg = self.reviews.aggregate(models.Avg("rating"))["rating__avg"]
        return round(avg, 1) if avg else 0.0

    @property
    def review_count(self):
        return self.reviews.count()

    def get_rating_breakdown(self):
        """Returns count and percentage for each star level (5 to 1) for Amazon-style rating breakdown."""
        total = self.reviews.count()
        if total == 0:
            return {star: {"count": 0, "percent": 0} for star in range(5, 0, -1)}
        breakdown = {}
        for star in range(5, 0, -1):
            c = self.reviews.filter(rating=star).count()
            breakdown[star] = {
                "count": c,
                "percent": round((c / total) * 100, 1),
            }
        return breakdown


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="gallery_images",
        help_text="Product associated with this gallery image"
    )
    image = models.ImageField(upload_to="products/gallery/")
    alt_text = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        if self.alt_text:
            return f"Gallery image for {self.product.name} ({self.alt_text})"
        return f"Gallery image for {self.product.name}"



class Wishlist(models.Model):
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="wishlist_items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="wishlisted_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "product")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.product.name}"


class Review(models.Model):
    RATING_CHOICES = [
        (5, "5 - Excellent"),
        (4, "4 - Very Good"),
        (3, "3 - Good"),
        (2, "2 - Fair"),
        (1, "1 - Poor"),
    ]

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
        default=5,
    )
    comment = models.TextField(
        blank=True,
        help_text="Customer written review feedback",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "product")
        ordering = ["-created_at"]

    @property
    def is_verified_purchase(self):
        """
        Validates if the reviewing customer actually purchased this gadget in a completed order.
        """
        from orders.models import OrderItem, Order
        return OrderItem.objects.filter(
            order__user=self.user,
            product=self.product,
            order__status__in=[Order.STATUS_PAID, Order.STATUS_SHIPPED, Order.STATUS_DELIVERED]
        ).exists()

    def __str__(self):
        return f"{self.user.email} - {self.product.name} ({self.rating}★)"
