from django.urls import path

from .views import (
    product_list_view,
    product_detail_view,
    product_compare_view,
    wishlist_view,
    toggle_wishlist_view,
)


app_name = "products"

urlpatterns = [
    # UI Routes
    path("", product_list_view, name="list"),
    path("compare/", product_compare_view, name="compare"),
    path("wishlist/", wishlist_view, name="wishlist"),
    path("wishlist/toggle/<int:product_id>/", toggle_wishlist_view, name="wishlist_toggle"),
    path("id/<int:pk>/", product_detail_view, name="detail_by_id"),
    path("<int:pk>/", product_detail_view, name="detail_by_pk"),
    path("<slug:slug>/", product_detail_view, name="detail"),
    path("<slug:slug>/view/", product_detail_view, name="product_detail"),
]