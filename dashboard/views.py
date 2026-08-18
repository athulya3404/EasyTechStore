from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count, Q
from datetime import datetime, timedelta

from orders.models import Order
from products.models import Product
from category.models import Category
from electronics_shopping_website.users.models import User


def is_site_manager(user):
    """Check if user is a site manager (staff but not superuser)"""
    return user.is_staff and not user.is_superuser


def is_superadmin(user):
    """Check if user is a superadmin"""
    return user.is_staff and user.is_superuser


@login_required
def site_manager_dashboard(request):
    """Main Site Manager Dashboard - Overview"""
    if not is_site_manager(request.user) and not is_superadmin(request.user):
        return render(request, 'dashboard/access_denied.html', status=403)
    
    # Dashboard Statistics
    total_orders = Order.objects.count()
    pending_orders = Order.objects.filter(status='Pending').count()
    completed_orders = Order.objects.filter(status='Completed').count()
    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    total_categories = Category.objects.count()
    total_users = User.objects.filter(is_staff=False).count()
    
    # Calculate total revenue
    total_revenue = Order.objects.aggregate(
        total=Sum('total_price')
    )['total'] or 0
    
    # Recent orders
    recent_orders = Order.objects.all().order_by('-created_at')[:5]
    
    # Low stock products
    low_stock_products = Product.objects.filter(stock__lt=10).count()
    
    # Today's orders
    today = datetime.now().date()
    today_orders = Order.objects.filter(created_at__date=today).count()
    
    # This month's revenue
    current_month = datetime.now()
    month_start = current_month.replace(day=1)
    month_revenue = Order.objects.filter(
        created_at__date__gte=month_start.date()
    ).aggregate(total=Sum('total_price'))['total'] or 0

    context = {
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "completed_orders": completed_orders,
        "total_products": total_products,
        "active_products": active_products,
        "total_categories": total_categories,
        "total_users": total_users,
        "total_revenue": total_revenue,
        "recent_orders": recent_orders,
        "low_stock_products": low_stock_products,
        "today_orders": today_orders,
        "month_revenue": month_revenue,
    }
    return render(request, "dashboard/site_manager_dashboard.html", context)


@login_required
def manage_categories(request):
    """Manage Categories"""
    if not is_site_manager(request.user) and not is_superadmin(request.user):
        return render(request, 'dashboard/access_denied.html', status=403)
    
    categories = Category.objects.all()
    context = {
        "categories": categories,
        "page_title": "Manage Categories",
        "section": "categories",
    }
    return render(request, "dashboard/manage_categories.html", context)


@login_required
def manage_brands(request):
    """Manage Brands (Placeholder - can be expanded if brand model exists)"""
    if not is_site_manager(request.user) and not is_superadmin(request.user):
        return render(request, 'dashboard/access_denied.html', status=403)
    
    # Placeholder - implement when Brand model is available
    context = {
        "page_title": "Manage Brands",
        "section": "brands",
    }
    return render(request, "dashboard/manage_brands.html", context)


@login_required
def manage_products(request):
    """Manage Products"""
    if not is_site_manager(request.user) and not is_superadmin(request.user):
        return render(request, 'dashboard/access_denied.html', status=403)
    
    products = Product.objects.all()
    total_products = products.count()
    active_products = products.filter(is_active=True).count()
    inactive_products = products.filter(is_active=False).count()
    
    context = {
        "products": products,
        "total_products": total_products,
        "active_products": active_products,
        "inactive_products": inactive_products,
        "page_title": "Manage Products",
        "section": "products",
    }
    return render(request, "dashboard/manage_products.html", context)


@login_required
def manage_users(request):
    """Manage Users"""
    if not is_site_manager(request.user) and not is_superadmin(request.user):
        return render(request, 'dashboard/access_denied.html', status=403)
    
    users = User.objects.filter(is_staff=False)
    total_users = users.count()
    active_users = users.filter(is_active=True).count()
    
    context = {
        "users": users,
        "total_users": total_users,
        "active_users": active_users,
        "page_title": "Manage Users",
        "section": "users",
    }
    return render(request, "dashboard/manage_users.html", context)


@login_required
def view_orders(request):
    """View All Orders"""
    if not is_site_manager(request.user) and not is_superadmin(request.user):
        return render(request, 'dashboard/access_denied.html', status=403)
    
    orders = Order.objects.all().order_by('-created_at')
    total_orders = orders.count()
    pending = orders.filter(status='Pending').count()
    completed = orders.filter(status='Completed').count()
    
    context = {
        "orders": orders,
        "total_orders": total_orders,
        "pending": pending,
        "completed": completed,
        "page_title": "View Orders",
        "section": "orders",
    }
    return render(request, "dashboard/view_orders.html", context)


@login_required
def update_order_status(request, order_id):
    """Update Order Status"""
    if not is_site_manager(request.user) and not is_superadmin(request.user):
        return render(request, 'dashboard/access_denied.html', status=403)
    
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return render(request, 'dashboard/order_not_found.html', status=404)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['Pending', 'Processing', 'Shipped', 'Completed', 'Cancelled']:
            order.status = new_status
            order.save()
            return render(request, 'dashboard/order_updated.html', {'order': order})
    
    context = {
        "order": order,
        "page_title": f"Update Order #{order.id}",
        "section": "orders",
    }
    return render(request, "dashboard/update_order_status.html", context)


@login_required
def sales_reports(request):
    """View Sales Reports"""
    if not is_site_manager(request.user) and not is_superadmin(request.user):
        return render(request, 'dashboard/access_denied.html', status=403)
    
    # Get date filter from request
    days = int(request.GET.get('days', 30))
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Get orders in date range
    orders = Order.objects.filter(created_at__date__gte=start_date.date())
    
    # Calculate metrics
    total_revenue = orders.aggregate(total=Sum('total_price'))['total'] or 0
    total_orders = orders.count()
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
    
    # Top products
    top_products = Product.objects.annotate(
        order_count=Count('orderitem')
    ).order_by('-order_count')[:10]
    
    # Revenue by category
    category_revenue = {}
    for category in Category.objects.all():
        revenue = Product.objects.filter(
            category=category
        ).aggregate(
            total=Sum('orderitem__order__total_price')
        )['total'] or 0
        category_revenue[category.name] = revenue
    
    context = {
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "avg_order_value": avg_order_value,
        "top_products": top_products,
        "category_revenue": category_revenue,
        "days": days,
        "page_title": "Sales Reports",
        "section": "reports",
    }
    return render(request, "dashboard/sales_reports.html", context)


@staff_member_required
def store_dashboard_view(request):
    total_orders = Order.objects.count()
    pending_orders = Order.objects.filter(status='Pending').count()
    total_products = Product.objects.count()
    
    # Calculate total revenue
    total_revenue = Order.objects.aggregate(
        total=Sum('total_price')
    )['total'] or 0

    context = {
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "total_products": total_products,
        "total_revenue": total_revenue,
    }
    return render(request, "dashboard/main.html", context)