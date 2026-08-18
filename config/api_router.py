from django.conf import settings

from rest_framework.routers import DefaultRouter, SimpleRouter

from electronics_shopping_website.users.api.views import UserViewSet
from products.views import ProductViewSet


# Use DefaultRouter in development so the browsable API is available.
# Use SimpleRouter in production.
router = DefaultRouter() if settings.DEBUG else SimpleRouter()


# User API
router.register(r"users", UserViewSet, basename="user")

# Product API
router.register(r"products", ProductViewSet, basename="product")


app_name = "api"

urlpatterns = router.urls