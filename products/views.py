from django.shortcuts import get_object_or_404, render
from rest_framework import viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny

from .models import Product
from .serializers import ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    """
    API ViewSet for products.
    """

    queryset = Product.objects.select_related("category").all()
    serializer_class = ProductSerializer

    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()

        category_id = self.request.query_params.get("category")

        if category_id:
            queryset = queryset.filter(category_id=category_id)

        return queryset


def product_list_view(request):
    """
    Fetches all active products and renders the homepage.
    """
    products = (
        Product.objects
        .filter(is_active=True)
        .select_related("category")
    )

    return render(
        request,
        "pages/home.html",
        {"products": products},
    )


def product_detail_view(request, pk):
    """
    Fetches a single active product by its primary key
    and renders the product detail page.
    """
    product = get_object_or_404(
        Product.objects.select_related("category"),
        pk=pk,
        is_active=True,
    )

    return render(
        request,
        "products/product_detail.html",
        {"product": product},
    )