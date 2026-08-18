from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import checkout_view, OrderViewSet

app_name = "orders"

# API Router for the OrderViewSet
router = DefaultRouter()
router.register("api/orders", OrderViewSet, basename="orders-api")

urlpatterns = [
    # UI View
    path("checkout/", checkout_view, name="checkout"),
    
    # API View
    path("", include(router.urls)),
]