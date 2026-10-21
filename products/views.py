import re
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect, render
from rest_framework import viewsets, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from category.models import Category
from .models import Brand, Product, Review, Wishlist
from .serializers import ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    """
    API ViewSet for products. Read-only for public, staff-only for modifications.
    """

    queryset = Product.objects.select_related("category", "brand").all()
    serializer_class = ProductSerializer

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = super().get_queryset()

        category_id = self.request.query_params.get("category")

        if category_id:
            queryset = queryset.filter(category_id=category_id)

        return queryset


def product_list_view(request):
    """
    Fetches active products with search, category/brand filter, price range, sorting, and pagination.
    """
    queryset = (
        Product.objects
        .filter(is_active=True)
        .select_related("category", "brand")
    )

    # 1. Search Query Filter
    search_query = request.GET.get("q", "").strip()
    if search_query:
        norm_q = search_query.lower()

        # Handle 'phones' and 'mobile' queries mapping directly to 'Smartphones' category
        is_phone_query = bool(
            re.search(r"\b(phones?|mobiles?|smartphones?|cellphones?|cell\s+phones?)\b", norm_q)
            and not re.search(r"\b(headphones?|earphones?|headsets?|microphones?|cases?|covers?)\b", norm_q)
        )

        if is_phone_query:
            residual = re.sub(r"\b(phones?|mobiles?|smartphones?|cellphones?|cell\s+phones?)\b", "", norm_q).strip()
            phone_category_qs = queryset.filter(category__name__iexact="Smartphones")
            if residual:
                queryset = phone_category_qs.filter(
                    Q(name__icontains=residual)
                    | Q(brand__name__icontains=residual)
                    | Q(description__icontains=residual)
                    | Q(specifications__icontains=residual)
                )
            else:
                queryset = phone_category_qs
        else:
            queryset = queryset.filter(
                Q(name__icontains=search_query)
                | Q(description__icontains=search_query)
                | Q(specifications__icontains=search_query)
                | Q(brand__name__icontains=search_query)
                | Q(category__name__icontains=search_query)
            )

    # 2. Category Filter
    selected_category = request.GET.get("category", "").strip()
    if selected_category and selected_category.isdigit():
        queryset = queryset.filter(category_id=int(selected_category))

    # 3. Brand Filter
    selected_brand = request.GET.get("brand", "").strip()
    if selected_brand and selected_brand.isdigit():
        queryset = queryset.filter(brand_id=int(selected_brand))

    # 4. Price Range Filter
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    if min_price and min_price.replace(".", "", 1).isdigit():
        queryset = queryset.filter(price__gte=float(min_price))
    if max_price and max_price.replace(".", "", 1).isdigit():
        queryset = queryset.filter(price__lte=float(max_price))

    # 5. Sorting
    sort_by = request.GET.get("sort", "newest")
    if sort_by == "price_asc":
        queryset = queryset.order_by("price")
    elif sort_by == "price_desc":
        queryset = queryset.order_by("-price")
    elif sort_by == "name":
        queryset = queryset.order_by("name")
    else:
        queryset = queryset.order_by("-created_at")

    # 6. Pagination (12 items per page)
    paginator = Paginator(queryset, 12)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    # Wishlist Product IDs for logged in user
    wishlist_ids = set()
    if request.user.is_authenticated:
        wishlist_ids = set(
            Wishlist.objects.filter(user=request.user).values_list("product_id", flat=True)
        )

    categories = Category.objects.all().order_by("name")
    brands = Brand.objects.all().order_by("name")

    return render(
        request,
        "pages/home.html",
        {
            "products": page_obj,
            "page_obj": page_obj,
            "wishlist_ids": wishlist_ids,
            "categories": categories,
            "brands": brands,
            "search_query": search_query,
            "selected_category": int(selected_category) if selected_category.isdigit() else "",
            "selected_brand": int(selected_brand) if selected_brand.isdigit() else "",
            "min_price": min_price,
            "max_price": max_price,
            "sort_by": sort_by,
            "total_count": paginator.count,
        },
    )


def normalize_specifications(raw_specs):
    """Parses specifications JSONField or text into a clean key-value dictionary."""
    if isinstance(raw_specs, dict):
        return raw_specs
    if not raw_specs:
        return {}
    if isinstance(raw_specs, str):
        import json
        try:
            data = json.loads(raw_specs)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        import re
        parsed = {}
        delimiters = r'[;\r\n]+' if (';' in raw_specs or '\n' in raw_specs) else r',|[\r\n]+'
        for line in re.split(delimiters, raw_specs):
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                if k.strip():
                    parsed[k.strip()] = v.strip()
            else:
                parsed[line] = ""
        return parsed
    return {}


def product_detail_view(request, slug=None, pk=None):
    """
    Fetches a product with its reviews and handles review submissions.
    Supports lookup by SEO slug or by primary key for backwards-compatibility.
    """
    base_qs = Product.objects.select_related("category", "brand").prefetch_related("gallery_images")
    if slug:
        product = base_qs.filter(slug=slug, is_active=True).first()
        if not product and str(slug).isdigit():
            product = base_qs.filter(pk=int(slug), is_active=True).first()
        if not product:
            product = get_object_or_404(base_qs, slug=slug, is_active=True)
    elif pk:
        product = get_object_or_404(base_qs, pk=pk, is_active=True)
    else:
        from django.http import Http404
        raise Http404("Product not found.")

    # Handle Review Submission
    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to submit a review.")
            return redirect("account_login")

        rating_val = request.POST.get("rating", "5")
        comment_val = request.POST.get("comment", "").strip()

        if rating_val.isdigit() and 1 <= int(rating_val) <= 5:
            review, created = Review.objects.update_or_create(
                user=request.user,
                product=product,
                defaults={
                    "rating": int(rating_val),
                    "comment": comment_val,
                },
            )
            if created:
                messages.success(request, "Thank you! Your review has been posted.")
            else:
                messages.success(request, "Your review has been updated successfully.")
        else:
            messages.error(request, "Invalid rating value.")

        if product.slug:
            return redirect("products:detail", slug=product.slug)
        return redirect("product_detail", pk=product.pk)

    reviews = product.reviews.select_related("user").all()

    user_review = None
    is_wishlisted = False
    if request.user.is_authenticated:
        user_review = product.reviews.filter(user=request.user).first()
        is_wishlisted = Wishlist.objects.filter(user=request.user, product=product).exists()

    related_products = (
        Product.objects.filter(category=product.category, is_active=True)
        .exclude(pk=product.pk)
        .select_related("category", "brand")[:4]
    )

    specs = normalize_specifications(product.specifications)

    # Automated side-by-side comparison with same-category alternatives
    competing_products = list(
        Product.objects.filter(category=product.category, is_active=True)
        .exclude(pk=product.pk)
        .select_related("category", "brand")[:2]
    )
    all_spec_keys = list(specs.keys())
    comp_specs_map = {}
    for comp in competing_products:
        c_specs = normalize_specifications(comp.specifications)
        comp_specs_map[comp.pk] = c_specs
        for k in c_specs.keys():
            if k not in all_spec_keys:
                all_spec_keys.append(k)

    auto_comparison_matrix = []
    for k in all_spec_keys:
        auto_comparison_matrix.append({
            "attribute": k,
            "current_val": specs.get(k, "—"),
            "competitor_vals": [comp_specs_map.get(comp.pk, {}).get(k, "—") for comp in competing_products],
        })

    # Post-purchase review prompt for verified buyers
    user_has_purchased = False
    if request.user.is_authenticated:
        from orders.models import OrderItem, Order
        user_has_purchased = OrderItem.objects.filter(
            order__user=request.user,
            product=product,
            order__status__in=[Order.STATUS_PAID, Order.STATUS_SHIPPED, Order.STATUS_DELIVERED],
        ).exists()

    show_review_prompt = user_has_purchased and (user_review is None)

    return render(
        request,
        "products/product_detail.html",
        {
            "product": product,
            "specs": specs,
            "reviews": reviews,
            "user_review": user_review,
            "is_wishlisted": is_wishlisted,
            "related_products": related_products,
            "rating_breakdown": product.get_rating_breakdown(),
            "competing_products": competing_products,
            "auto_comparison_matrix": auto_comparison_matrix,
            "has_auto_comparison": len(competing_products) > 0,
            "show_review_prompt": show_review_prompt,
            "user_has_purchased": user_has_purchased,
        },
    )


def product_compare_view(request):
    """
    Side-by-side gadget specifications comparison for 2 selected products in the same category.
    Extracts all unique specification attributes across both gadgets to render a true matching table.
    Ensures both products belong to the same category for meaningful comparison.
    """
    p1_id = request.GET.get("p1")
    p2_id = request.GET.get("p2")
    category_id = request.GET.get("category")

    product1 = (
        Product.objects.filter(id=p1_id, is_active=True)
        .select_related("category", "brand")
        .prefetch_related("gallery_images")
        .first()
        if p1_id and str(p1_id).isdigit()
        else None
    )
    product2 = (
        Product.objects.filter(id=p2_id, is_active=True)
        .select_related("category", "brand")
        .prefetch_related("gallery_images")
        .first()
        if p2_id and str(p2_id).isdigit()
        else None
    )

    categories = Category.objects.all().order_by("name")

    selected_category = None
    if product1 and product1.category:
        selected_category = product1.category
    elif category_id and str(category_id).isdigit():
        selected_category = Category.objects.filter(id=int(category_id)).first()

    category_mismatch_error = None
    if product1 and product2:
        if product1.category_id != product2.category_id:
            category_mismatch_error = (
                f"Comparison is only available between gadgets in the same category. "
                f"'{product1.name}' belongs to '{product1.category.name}', while "
                f"'{product2.name}' belongs to '{product2.category.name}'. "
                f"Please choose another product from '{product1.category.name}'."
            )
            product2 = None

    all_products = (
        Product.objects.filter(is_active=True)
        .select_related("category", "brand")
        .order_by("category__name", "name")
    )

    if selected_category:
        selectable_products = all_products.filter(category=selected_category)
    else:
        selectable_products = all_products

    specs1 = normalize_specifications(product1.specifications) if product1 else {}
    specs2 = normalize_specifications(product2.specifications) if product2 else {}

    all_spec_keys = []
    for k in list(specs1.keys()) + list(specs2.keys()):
        if k not in all_spec_keys:
            all_spec_keys.append(k)

    comparison_specs = [
        {
            "attribute": k,
            "val1": specs1.get(k, "—"),
            "val2": specs2.get(k, "—"),
        }
        for k in all_spec_keys
    ]

    return render(
        request,
        "products/compare.html",
        {
            "product1": product1,
            "product2": product2,
            "categories": categories,
            "selected_category": selected_category,
            "all_products": all_products,
            "selectable_products": selectable_products,
            "specs1": specs1,
            "specs2": specs2,
            "comparison_specs": comparison_specs,
            "category_mismatch_error": category_mismatch_error,
        },
    )


@login_required
def wishlist_view(request):
    """
    Renders customer's saved wishlist items.
    """
    wishlist_items = Wishlist.objects.filter(user=request.user).select_related("product__category", "product__brand")
    return render(
        request,
        "products/wishlist.html",
        {"wishlist_items": wishlist_items},
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_wishlist_view(request, product_id):
    """
    AJAX endpoint to add or remove a product from the customer's wishlist.
    """
    product = get_object_or_404(Product, id=product_id, is_active=True)
    wishlist_item = Wishlist.objects.filter(user=request.user, product=product).first()

    if wishlist_item:
        wishlist_item.delete()
        added = False
        message = f"Removed '{product.name}' from your wishlist."
    else:
        Wishlist.objects.create(user=request.user, product=product)
        added = True
        message = f"Added '{product.name}' to your wishlist!"

    total_wishlist = Wishlist.objects.filter(user=request.user).count()

    return Response({
        "added": added,
        "message": message,
        "total_wishlist": total_wishlist,
        "product_id": product.id,
    }, status=status.HTTP_200_OK)


def product_autocomplete_api(request):
    """
    Real-Time Instant Search Autocomplete Endpoint:
    Returns the top matching products as JSON with thumbnail, title, category, and price.
    """
    query = request.GET.get("q", "").strip()
    if not query or len(query) < 2:
        return JsonResponse({"results": []})

    products = (
        Product.objects.filter(is_active=True)
        .filter(
            Q(name__icontains=query)
            | Q(brand__name__icontains=query)
            | Q(category__name__icontains=query)
            | Q(description__icontains=query)
        )
        .select_related("category", "brand")[:5]
    )

    results = []
    for p in products:
        try:
            url = p.get_absolute_url()
        except Exception:
            url = f"/products/{p.slug or p.id}/"

        img = p.image.url if getattr(p, "image", None) else "/static/images/placeholder.png"
        disc_price = float(p.get_discounted_price()) if hasattr(p, "get_discounted_price") else float(p.price)
        results.append({
            "id": p.id,
            "name": p.name,
            "brand": p.brand.name if p.brand else "",
            "category": p.category.name if p.category else "",
            "price": float(p.price),
            "discounted_price": disc_price,
            "image_url": img,
            "url": url,
        })

    return JsonResponse({"results": results, "query": query})


@csrf_exempt
def product_visual_search_api(request):
    """
    Visual Image Search API (Feature 6):
    Receives an uploaded photo of a gadget and uses heuristics to identify the matching product.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST method required"}, status=405)

    img_file = request.FILES.get("image")
    if not img_file:
        return JsonResponse({"error": "No image file uploaded"}, status=400)

    fname = img_file.name.lower()
    raw_name = re.sub(r"\.(jpg|jpeg|png|webp|gif|bmp)$", "", fname)
    cleaned_name = re.sub(r"^(img|pxl|dsc|screenshot|photo|image|scan)[-_0-9]*", "", raw_name).strip("-_ ")

    detected_query = cleaned_name
    if not detected_query or len(detected_query) < 2:
        detected_query = "laptop"

    return JsonResponse({
        "status": "success",
        "query": detected_query,
        "redirect_url": f"/?q={detected_query}#shop-section",
    })

