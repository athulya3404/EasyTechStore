from django.shortcuts import render
from django.contrib.auth import get_user_model
from django.db.models import Sum

from products.models import Product, Brand
from category.models import Category
from orders.models import Order

from .decorators import manager_required, superadmin_required
from .views_products import (
    manager_products,
    product_add,
    product_edit,
    product_detail,
    product_delete,
    product_bulk_delete,
    manager_inventory,
    product_import,
    product_import_parse,
    product_import_item,
    product_sample_template,
)
from .views_categories import (
    manager_categories,
    category_add,
    category_edit,
    category_delete,
    category_import,
    category_sample_template,
)
from .views_brands import (
    manager_brands,
    brand_add,
    brand_edit,
    brand_delete,
    brand_import,
    brand_sample_template,
)
from .views_orders import (
    manager_orders,
    order_detail,
    update_order_status,
    trigger_auto_delivery_sweep,
)
from .views_reports import (
    sales_reports,
    export_sales_report_csv,
    get_sales_stats,
)
from .views_users import (
    manager_users,
    user_toggle_status,
    manager_user_detail,
)
from .views_chatbot import (
    manager_chatbot_conversations,
)
from .services_importer import (
    parse_product_spreadsheet_rows,
    save_single_imported_product,
)

User = get_user_model()


def get_dashboard_stats():
    """Calculate and return dashboard statistics matching required 6 summary metrics with database-level aggregation"""
    total_products = Product.objects.count()
    total_categories = Category.objects.count()
    total_brands = Brand.objects.count()
    total_orders = Order.objects.count()
    pending_orders = Order.objects.filter(status='Pending').count()
    low_stock_products = Product.objects.filter(stock__lte=10).count()
    
    # Total unique registered customers
    total_customers = User.objects.filter(is_staff=False, is_superuser=False).count()
    if total_customers == 0:
        total_customers = Order.objects.values('user').distinct().count()

    # Database-level revenue aggregation (Problem 9.2 fix)
    total_revenue = float(
        Order.objects.filter(
            status__in=['Paid', 'Shipped', 'Delivered']
        ).aggregate(total=Sum('total_amount'))['total'] or 0.0
    )
    
    recent_orders = Order.objects.select_related('user').prefetch_related('items__product').order_by('-created_at')[:5]
    low_stock_items = Product.objects.select_related('category', 'brand').filter(stock__lte=10).order_by('stock')[:5]

    # 7-Day Revenue & Sales Volume Trends
    from django.utils import timezone
    from datetime import timedelta
    import json

    now = timezone.now()
    seven_days_labels = []
    seven_days_revenue = []
    seven_days_orders = []

    for i in range(6, -1, -1):
        day_date = (now - timedelta(days=i)).date()
        seven_days_labels.append(day_date.strftime("%b %d"))
        day_paid_orders = Order.objects.filter(
            created_at__date=day_date,
            status__in=['Paid', 'Shipped', 'Delivered']
        )
        rev = float(day_paid_orders.aggregate(s=Sum('total_amount'))['s'] or 0.0)
        cnt = Order.objects.filter(created_at__date=day_date).count()
        seven_days_revenue.append(round(rev, 2))
        seven_days_orders.append(cnt)

    # Inventory Health Breakdown
    in_stock_count = Product.objects.filter(stock__gt=10).count()
    low_stock_count = Product.objects.filter(stock__gt=0, stock__lte=10).count()
    out_of_stock_count = Product.objects.filter(stock=0).count()

    # Chatbot Query Metrics
    try:
        from chatbot.models import ChatMessage
        chatbot_queries = ChatMessage.objects.filter(sender="user").count()
    except Exception:
        chatbot_queries = 0

    return {
        'total_products': total_products,
        'total_categories': total_categories,
        'total_brands': total_brands,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'low_stock_products': low_stock_products,
        'total_customers': total_customers,
        'total_revenue': total_revenue,
        'recent_orders': recent_orders,
        'low_stock_items': low_stock_items,
        'in_stock_count': in_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'chatbot_queries': chatbot_queries,
        'chart_revenue_labels': json.dumps(seven_days_labels),
        'chart_revenue_data': json.dumps(seven_days_revenue),
        'chart_orders_data': json.dumps(seven_days_orders),
        'chart_stock_labels': json.dumps(["Healthy (>10)", "Low Stock (1-10)", "Out of Stock (0)"]),
        'chart_stock_data': json.dumps([in_stock_count, low_stock_count, out_of_stock_count]),
    }


@manager_required
def manager_home(request):
    """Main manager dashboard home page"""
    context = get_dashboard_stats()
    return render(request, 'manager/managerhome.html', context)
