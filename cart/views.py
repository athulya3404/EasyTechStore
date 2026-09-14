from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from products.models import Product
from .models import Cart, CartItem
from .recommendations import get_recommended_products_for_user
from .serializers import CartSerializer


@login_required
def cart_detail_view(request):
    """Renders the HTML page for the user's shopping cart."""
    cart, created = Cart.objects.get_or_create(user=request.user)
    recommended_products = get_recommended_products_for_user(request.user, cart)
    return render(
        request,
        "cart/cart_detail.html",
        {
            "cart": cart,
            "recommended_products": recommended_products,
        }
    )


class CartViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    def get_object(self):
        # Get the cart for the current user, or create it if it doesn't exist
        cart, created = Cart.objects.get_or_create(user=self.request.user)
        return cart

    def list(self, request):
        """View Cart and Calculate Total Price"""
        cart = self.get_object()
        serializer = self.get_serializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def add_item(self, request):
        """Add Product to Cart with validation and stock check"""
        cart = self.get_object()
        product_id = request.data.get('product_id')
        try:
            quantity = int(request.data.get('quantity', 1))
            if quantity <= 0:
                return Response({"error": "Quantity must be greater than 0."}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({"error": "Invalid quantity."}, status=status.HTTP_400_BAD_REQUEST)

        product = get_object_or_404(Product, id=product_id, is_active=True)

        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
        new_quantity = cart_item.quantity + quantity if not created else quantity

        # Stock check
        if new_quantity > product.stock:
            return Response(
                {"error": f"Cannot add {quantity} item(s). Only {product.stock} left in stock."},
                status=status.HTTP_400_BAD_REQUEST
            )

        cart_item.quantity = new_quantity
        cart_item.save()

        serializer = self.get_serializer(cart)
        data = dict(serializer.data)
        data["cart_item_id"] = cart_item.id
        data["added_item_id"] = cart_item.id
        data["product_id"] = product.id
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch', 'post'], url_path='update_quantity/(?P<item_id>[^/.]+)')
    def update_quantity(self, request, item_id=None):
        """Update Quantity of an Item in the Cart"""
        cart = self.get_object()
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
        
        try:
            quantity = int(request.data.get('quantity', 1))
        except (ValueError, TypeError):
            return Response({"error": "Invalid quantity."}, status=status.HTTP_400_BAD_REQUEST)

        if quantity > 0:
            if quantity > cart_item.product.stock:
                return Response(
                    {"error": f"Only {cart_item.product.stock} units available in stock."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            cart_item.quantity = quantity
            cart_item.save()
        else:
            cart_item.delete()

        serializer = self.get_serializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['delete', 'post'], url_path='remove_item/(?P<item_id>[^/.]+)')
    def remove_item(self, request, item_id=None):
        """Remove Product from Cart"""
        cart = self.get_object()
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
        cart_item.delete()

        serializer = self.get_serializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)