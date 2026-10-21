from django.db.models import Q
from products.models import Product
from orders.models import OrderItem


def get_recommended_products_for_user(user, cart, limit=4):
    """
    Finds recommended products matching the user's preferences:
    - Analyzes categories and brands from user's wishlist, past order history, and current cart items.
    - Excludes all products already chosen by the user in their cart.
    - Recommended items are ONLY displayed as suggestions with an explicit '+ Add to Cart' button;
      they are NEVER automatically added to the cart or checkout.
    """
    cart_product_ids = [pid for pid in cart.items.values_list('product_id', flat=True) if pid] if cart else []

    preferred_category_ids = set()
    preferred_brand_ids = set()

    # 1. Preferences from current cart items
    if cart:
        for item in cart.items.filter(product__isnull=False).select_related('product'):
            if item.product:
                if item.product.category_id:
                    preferred_category_ids.add(item.product.category_id)
                if item.product.brand_id:
                    preferred_brand_ids.add(item.product.brand_id)

    # 2. Preferences from user's wishlist and order history
    if user and user.is_authenticated:
        if hasattr(user, 'wishlist_items'):
            for w in user.wishlist_items.filter(product__isnull=False).select_related('product'):
                if w.product:
                    if w.product.category_id:
                        preferred_category_ids.add(w.product.category_id)
                    if w.product.brand_id:
                        preferred_brand_ids.add(w.product.brand_id)

        past_order_items = OrderItem.objects.filter(
            order__user=user,
            product__isnull=False
        ).select_related('product')[:25]
        for oi in past_order_items:
            if oi.product:
                if oi.product.category_id:
                    preferred_category_ids.add(oi.product.category_id)
                if oi.product.brand_id:
                    preferred_brand_ids.add(oi.product.brand_id)

    base_qs = Product.objects.filter(
        is_active=True,
        stock__gt=0
    ).exclude(id__in=cart_product_ids).select_related('category', 'brand')

    recommended = []
    if preferred_category_ids or preferred_brand_ids:
        pref_query = Q()
        if preferred_category_ids:
            pref_query |= Q(category_id__in=preferred_category_ids)
        if preferred_brand_ids:
            pref_query |= Q(brand_id__in=preferred_brand_ids)

        recommended = list(base_qs.filter(pref_query).order_by('-discount', '-created_at')[:limit])

    # If fewer than limit, backfill with top active in-stock gadgets
    if len(recommended) < limit:
        existing_ids = cart_product_ids + [p.id for p in recommended]
        fallback = list(
            Product.objects.filter(is_active=True, stock__gt=0)
            .exclude(id__in=existing_ids)
            .select_related('category', 'brand')
            .order_by('-discount', '-created_at')[:limit - len(recommended)]
        )
        recommended.extend(fallback)

    return recommended
