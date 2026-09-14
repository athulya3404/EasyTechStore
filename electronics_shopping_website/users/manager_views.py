"""
Modularized Manager Views Facade
Exposes all manager sub-modules for backwards-compatibility while delegating
to single-responsibility domain packages in users.manager:
- users.manager.views_products
- users.manager.views_categories
- users.manager.views_brands
- users.manager.views_orders
- users.manager.views_reports
- users.manager.views_users
- users.manager.services_importer
- users.manager.decorators
"""

from .manager import (
    # Permissions
    manager_required,
    superadmin_required,
    
    # Dashboard Home & Stats
    manager_home,
    get_dashboard_stats,
    get_sales_stats,
    
    # Products & Inventory
    manager_products,
    product_add,
    product_edit,
    product_detail,
    product_delete,
    product_bulk_delete,
    manager_inventory,
    
    # Product Ingestion & Templates
    product_import,
    product_import_parse,
    product_import_item,
    product_sample_template,
    parse_product_spreadsheet_rows,
    save_single_imported_product,
    
    # Categories
    manager_categories,
    category_add,
    category_edit,
    category_delete,
    category_import,
    category_sample_template,
    
    # Brands
    manager_brands,
    brand_add,
    brand_edit,
    brand_delete,
    brand_import,
    brand_sample_template,
    
    # Orders
    manager_orders,
    order_detail,
    update_order_status,
    
    # Sales Reports
    sales_reports,
    export_sales_report_csv,
    
    # Users & Customers
    manager_users,
    user_toggle_status,
    manager_user_detail,
    
    # AI Chatbot Auditing
    manager_chatbot_conversations,
)
