from rest_framework import viewsets

from .models import Product
from .serializers import ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("category").all()
    serializer_class = ProductSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        category_id = self.request.query_params.get("category")

        if category_id:
            queryset = queryset.filter(
                category_id=category_id
            )

        return queryset