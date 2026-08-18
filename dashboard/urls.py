from django.urls import path
from .views import (
    store_dashboard_view,
    site_manager_dashboard,
    manage_categories,
    manage_brands,
    manage_products,
    manage_users,
    view_orders,
    update_order_status,
    sales_reports,
)

app_name = "dashboard"

urlpatterns = [
    path("", store_dashboard_view, name="main"),
    # Site Manager Dashboard
    path("site-manager/", site_manager_dashboard, name="site_manager"),
    path("categories/", manage_categories, name="categories"),
    path("brands/", manage_brands, name="brands"),
    path("products/", manage_products, name="products"),
    path("users/", manage_users, name="users"),
    path("orders/", view_orders, name="orders"),
    path("orders/<int:order_id>/update-status/", update_order_status, name="update_order_status"),
    path("reports/", sales_reports, name="reports"),
]