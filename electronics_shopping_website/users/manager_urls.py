"""
Manager Dashboard URL Configuration
Namespace: 'manager'
"""

from django.urls import path
from . import manager_views

app_name = "manager"

urlpatterns = [
    # Dashboard
    path("dashboard/home/", view=manager_views.manager_home, name="home"),
    
    # Products
    path("dashboard/products/", view=manager_views.manager_products, name="products"),
    path("dashboard/products/add/", view=manager_views.product_add, name="product_add"),
    path("dashboard/products/<int:pk>/edit/", view=manager_views.product_edit, name="product_edit"),
    path("dashboard/products/<int:pk>/detail/", view=manager_views.product_detail, name="product_detail"),
    path("dashboard/products/<int:pk>/delete/", view=manager_views.product_delete, name="product_delete"),
    
    # Categories
    path("dashboard/categories/", view=manager_views.manager_categories, name="categories"),
    path("dashboard/categories/add/", view=manager_views.category_add, name="category_add"),
    path("dashboard/categories/<int:pk>/edit/", view=manager_views.category_edit, name="category_edit"),
    path("dashboard/categories/<int:pk>/delete/", view=manager_views.category_delete, name="category_delete"),
    
    # Brands
    path("dashboard/brands/", view=manager_views.manager_brands, name="brands"),
    path("dashboard/brands/add/", view=manager_views.brand_add, name="brand_add"),
    path("dashboard/brands/<int:pk>/edit/", view=manager_views.brand_edit, name="brand_edit"),
    path("dashboard/brands/<int:pk>/delete/", view=manager_views.brand_delete, name="brand_delete"),
    
    # Inventory
    path("dashboard/inventory/", view=manager_views.manager_inventory, name="inventory"),
    
    # Orders
    path("dashboard/orders/", view=manager_views.manager_orders, name="orders"),
    path("dashboard/orders/<int:pk>/detail/", view=manager_views.order_detail, name="order_detail"),
    path("dashboard/orders/<int:pk>/update-status/", view=manager_views.update_order_status, name="update_order_status"),
    
    # Reports
    path("dashboard/reports/", view=manager_views.sales_reports, name="reports"),
]
