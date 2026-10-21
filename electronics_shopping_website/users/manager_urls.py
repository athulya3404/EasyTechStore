"""
Manager Dashboard URL Configuration
Namespace: 'manager'
"""

from django.urls import path
from . import manager_views

app_name = "manager"

urlpatterns = [
    # Dashboard Root & Home
    path("", view=manager_views.manager_home, name="index"),
    path("dashboard/home/", view=manager_views.manager_home, name="home"),
    
    # Products
    path("dashboard/products/", view=manager_views.manager_products, name="products"),
    path("dashboard/products/add/", view=manager_views.product_add, name="product_add"),
    path("dashboard/products/import/", view=manager_views.product_import, name="product_import"),
    path("dashboard/products/import/parse/", view=manager_views.product_import_parse, name="product_import_parse"),
    path("dashboard/products/import/item/", view=manager_views.product_import_item, name="product_import_item"),
    path("dashboard/products/sample-template/", view=manager_views.product_sample_template, name="product_sample_template"),
    path("dashboard/products/<int:pk>/edit/", view=manager_views.product_edit, name="product_edit"),
    path("dashboard/products/<int:pk>/detail/", view=manager_views.product_detail, name="product_detail"),
    path("dashboard/products/<int:pk>/delete/", view=manager_views.product_delete, name="product_delete"),
    path("dashboard/products/bulk-delete/", view=manager_views.product_bulk_delete, name="product_bulk_delete"),
    
    # Categories
    path("dashboard/categories/", view=manager_views.manager_categories, name="categories"),
    path("dashboard/categories/add/", view=manager_views.category_add, name="category_add"),
    path("dashboard/categories/import/", view=manager_views.category_import, name="category_import"),
    path("dashboard/categories/sample-template/", view=manager_views.category_sample_template, name="category_sample_template"),
    path("dashboard/categories/<int:pk>/edit/", view=manager_views.category_edit, name="category_edit"),
    path("dashboard/categories/<int:pk>/delete/", view=manager_views.category_delete, name="category_delete"),
    
    # Brands
    path("dashboard/brands/", view=manager_views.manager_brands, name="brands"),
    path("dashboard/brands/add/", view=manager_views.brand_add, name="brand_add"),
    path("dashboard/brands/import/", view=manager_views.brand_import, name="brand_import"),
    path("dashboard/brands/sample-template/", view=manager_views.brand_sample_template, name="brand_sample_template"),
    path("dashboard/brands/<int:pk>/edit/", view=manager_views.brand_edit, name="brand_edit"),
    path("dashboard/brands/<int:pk>/delete/", view=manager_views.brand_delete, name="brand_delete"),
    
    # Inventory
    path("dashboard/inventory/", view=manager_views.manager_inventory, name="inventory"),
    
    # Orders
    path("dashboard/orders/", view=manager_views.manager_orders, name="orders"),
    path("dashboard/orders/auto-delivery-sweep/", view=manager_views.trigger_auto_delivery_sweep, name="auto_delivery_sweep"),
    path("dashboard/orders/<int:pk>/detail/", view=manager_views.order_detail, name="order_detail"),
    path("dashboard/orders/<int:pk>/update-status/", view=manager_views.update_order_status, name="update_order_status"),
    
    # Reports
    path("dashboard/reports/", view=manager_views.sales_reports, name="reports"),
    path("dashboard/reports/export-csv/", view=manager_views.export_sales_report_csv, name="export_sales_csv"),
    
    # Customer / User Management
    path("dashboard/users/", view=manager_views.manager_users, name="users"),
    path("dashboard/users/<int:pk>/", view=manager_views.manager_user_detail, name="user_detail_alias"),
    path("dashboard/users/<int:pk>/toggle-status/", view=manager_views.user_toggle_status, name="user_toggle_status"),
    path("dashboard/users/<int:pk>/detail/", view=manager_views.manager_user_detail, name="user_detail"),
    
    # AI Chatbot Conversations Monitoring
    path("dashboard/conversations/", view=manager_views.manager_chatbot_conversations, name="chatbot_conversations"),
]
