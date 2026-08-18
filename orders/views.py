from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from cart.models import Cart
from .models import Order, OrderItem

@login_required
def checkout_view(request):
    """Renders the checkout page. Redirects to cart if cart is empty."""
    cart, created = Cart.objects.get_or_create(user=request.user)
    
    # Don't let users check out an empty cart
    if not cart.items.exists():
        return redirect('cart_detail')
        
    return render(request, "orders/checkout.html", {"cart": cart})


class OrderViewSet(viewsets.ViewSet):
    """API for managing orders and checkout."""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def place_order(self, request):
        """Converts the active cart into a confirmed order."""
        cart = Cart.objects.filter(user=request.user).first()
        
        if not cart or not cart.items.exists():
            return Response(
                {"error": "Your cart is empty."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        shipping_address = request.data.get("shipping_address")
        if not shipping_address:
            return Response(
                {"error": "Shipping address is required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. Create the new Order
        order = Order.objects.create(
            user=request.user,
            shipping_address=shipping_address,
            status='Pending'
        )

        # 2. Move items from Cart to OrderItem (Locking in the current price)
        for cart_item in cart.items.all():
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                quantity=cart_item.quantity,
                price_at_purchase=cart_item.product.price # Save price historically
            )
            
            # Optional: Decrease product stock here!
            # cart_item.product.stock -= cart_item.quantity
            # cart_item.product.save()

        # 3. Clear the user's cart
        cart.items.all().delete()

        return Response({
            "message": "Order placed successfully!", 
            "order_id": order.id
        }, status=status.HTTP_201_CREATED)