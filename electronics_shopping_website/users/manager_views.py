"""
Manager Dashboard Views for Site Managers and Superadmins

All views in this module are restricted to users with is_staff=True or is_superuser=True
"""

from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Sum, Count, F
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import get_user_model

from products.models import Product, Brand
from category.models import Category
from orders.models import Order, OrderItem

User = get_user_model()


# ===== PERMISSION DECORATORS =====

def manager_required(view_func):
    """Decorator: Require user to be a site manager (is_staff=True) or superadmin"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('account_login')
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, "You do not have permission to access the manager dashboard.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


def superadmin_required(view_func):
    """Decorator: Require user to be a superadmin (is_superuser=True)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('account_login')
        if not request.user.is_superuser:
            messages.error(request, "You do not have permission to access this page.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


# ===== HELPER FUNCTIONS =====

def get_dashboard_stats():
    """Calculate and return dashboard statistics matching required 6 summary metrics"""
    total_products = Product.objects.count()
    total_categories = Category.objects.count()
    total_orders = Order.objects.count()
    pending_orders = Order.objects.filter(status='Pending').count()
    low_stock_products = Product.objects.filter(stock__lte=10).count()
    
    # Total unique registered customers
    total_customers = User.objects.filter(is_staff=False, is_superuser=False).count()
    if total_customers == 0:
        total_customers = Order.objects.values('user').distinct().count()

    # Calculate total revenue
    paid_orders = Order.objects.filter(status__in=['Paid', 'Shipped', 'Delivered'])
    total_revenue = sum(order.get_total_price() for order in paid_orders)
    
    recent_orders = Order.objects.select_related('user').prefetch_related('items__product').order_by('-created_at')[:5]
    low_stock_items = Product.objects.select_related('category', 'brand').filter(stock__lte=10).order_by('stock')[:5]

    return {
        'total_products': total_products,
        'total_categories': total_categories,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'low_stock_products': low_stock_products,
        'total_customers': total_customers,
        'total_revenue': total_revenue,
        'recent_orders': recent_orders,
        'low_stock_items': low_stock_items,
    }


def get_sales_stats():
    """Calculate and return detailed sales statistics"""
    paid_orders = Order.objects.filter(status__in=['Paid', 'Shipped', 'Delivered'])
    total_revenue = sum(order.get_total_price() for order in paid_orders)
    
    total_orders = Order.objects.count()
    completed_orders = Order.objects.filter(status__in=['Shipped', 'Delivered']).count()
    pending_orders = Order.objects.filter(status='Pending').count()
    paid_count = Order.objects.filter(status='Paid').count()
    
    average_order_value = (total_revenue / paid_orders.count()) if paid_orders.count() > 0 else 0
    
    return {
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'completed_orders': completed_orders,
        'pending_orders': pending_orders,
        'paid_count': paid_count,
        'average_order_value': average_order_value,
    }


# ===== DASHBOARD VIEWS =====

@manager_required
def manager_home(request):
    """Main manager dashboard home page"""
    context = get_dashboard_stats()
    return render(request, 'manager/managerhome.html', context)


# ===== PRODUCT MANAGEMENT =====

@manager_required
def manager_products(request):
    """Display list of all products with search and filtering"""
    products = Product.objects.select_related('category', 'brand').all()
    categories = Category.objects.all()
    brands = Brand.objects.all()
    
    # Search filter
    query = request.GET.get('q', '').strip()
    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(specifications__icontains=query) |
            Q(category__name__icontains=query) |
            Q(brand__name__icontains=query)
        )
    
    # Category filter
    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(category_id=category_id)
        
    # Brand filter
    brand_id = request.GET.get('brand')
    if brand_id:
        products = products.filter(brand_id=brand_id)

    # Availability filter
    availability = request.GET.get('availability')
    if availability == 'active':
        products = products.filter(is_active=True)
    elif availability == 'inactive':
        products = products.filter(is_active=False)
    elif availability == 'in_stock':
        products = products.filter(stock__gt=10)
    elif availability == 'low_stock':
        products = products.filter(stock__gt=0, stock__lte=10)
    elif availability == 'out_of_stock':
        products = products.filter(stock=0)
    
    context = {
        'products': products,
        'categories': categories,
        'brands': brands,
        'query': query,
        'selected_category': category_id,
        'selected_brand': brand_id,
        'selected_availability': availability,
        'total_count': products.count(),
    }
    return render(request, 'manager/products.html', context)


@manager_required
def product_add(request):
    """Create a new product with all required fields"""
    categories = Category.objects.all()
    brands = Brand.objects.all()
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            category_id = request.POST.get('category')
            brand_id = request.POST.get('brand') or None
            price = request.POST.get('price')
            discount = request.POST.get('discount', 0)
            stock = request.POST.get('stock', 0)
            description = request.POST.get('description', '').strip()
            specifications = request.POST.get('specifications', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            image = request.FILES.get('image')
            
            # Validation
            if not all([name, category_id, price, stock]):
                messages.error(request, "Please fill in all required fields (Name, Category, Price, Stock).")
                return render(request, 'manager/product_add.html', {
                    'categories': categories,
                    'brands': brands,
                    'form_data': request.POST,
                })
            
            category = get_object_or_404(Category, id=category_id)
            brand = get_object_or_404(Brand, id=brand_id) if brand_id else None
            
            product = Product(
                name=name,
                category=category,
                brand=brand,
                price=float(price),
                discount=float(discount) if discount else 0,
                stock=int(stock),
                description=description,
                specifications=specifications,
                image=image,
                is_active=is_active
            )
            product.save()
            
            messages.success(request, f"Product '{name}' created successfully!")
            return redirect('manager:products')
            
        except Exception as e:
            messages.error(request, f"Error creating product: {str(e)}")
            return render(request, 'manager/product_add.html', {
                'categories': categories,
                'brands': brands,
                'form_data': request.POST,
            })
    
    context = {
        'categories': categories,
        'brands': brands,
    }
    return render(request, 'manager/product_add.html', context)


@manager_required
def product_edit(request, pk):
    """Edit an existing product"""
    product = get_object_or_404(Product.objects.select_related('category', 'brand'), pk=pk)
    categories = Category.objects.all()
    brands = Brand.objects.all()
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name', product.name).strip()
            category_id = request.POST.get('category')
            brand_id = request.POST.get('brand') or None
            price = request.POST.get('price')
            discount = request.POST.get('discount', 0)
            stock = request.POST.get('stock')
            description = request.POST.get('description', product.description).strip()
            specifications = request.POST.get('specifications', product.specifications).strip()
            is_active = request.POST.get('is_active') == 'on'
            
            if not all([name, category_id, price, stock]):
                messages.error(request, "Please fill in all required fields.")
                return render(request, 'manager/product_edit.html', {
                    'product': product,
                    'categories': categories,
                    'brands': brands,
                })
            
            product.name = name
            product.category = get_object_or_404(Category, id=category_id)
            product.brand = get_object_or_404(Brand, id=brand_id) if brand_id else None
            product.price = float(price)
            product.discount = float(discount) if discount else 0
            product.stock = int(stock)
            product.description = description
            product.specifications = specifications
            product.is_active = is_active
            
            if 'image' in request.FILES:
                product.image = request.FILES['image']
            
            product.save()
            messages.success(request, f"Product '{product.name}' updated successfully!")
            return redirect('manager:products')
            
        except Exception as e:
            messages.error(request, f"Error updating product: {str(e)}")
    
    context = {
        'product': product,
        'categories': categories,
        'brands': brands,
    }
    return render(request, 'manager/product_edit.html', context)


@manager_required
def product_detail(request, pk):
    """Display full product details"""
    product = get_object_or_404(Product.objects.select_related('category', 'brand'), pk=pk)
    context = {'product': product}
    return render(request, 'manager/product_detail.html', context)


@manager_required
def product_delete(request, pk):
    """Delete a product with confirmation"""
    product = get_object_or_404(Product.objects.select_related('category', 'brand'), pk=pk)
    
    if request.method == 'POST':
        product_name = product.name
        product.delete()
        messages.success(request, f"Product '{product_name}' deleted successfully!")
        return redirect('manager:products')
    
    context = {'product': product}
    return render(request, 'manager/product_confirm_delete.html', context)


# ===== CATEGORY MANAGEMENT =====

@manager_required
def manager_categories(request):
    """Display list of all categories with product counts"""
    categories = Category.objects.annotate(product_count=Count('products')).order_by('name')
    context = {'categories': categories}
    return render(request, 'manager/categories.html', context)


@manager_required
def category_add(request):
    """Create a new category"""
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            is_active = request.POST.get('is_active') == 'on' or 'is_active' not in request.POST
            
            if not name:
                messages.error(request, "Category name is required.")
                return render(request, 'manager/category_add.html')
            
            if Category.objects.filter(name__iexact=name).exists():
                messages.error(request, f"A category with name '{name}' already exists.")
                return render(request, 'manager/category_add.html')
            
            category = Category(name=name, description=description, is_active=is_active)
            category.save()
            
            messages.success(request, f"Category '{name}' created successfully!")
            return redirect('manager:categories')
            
        except Exception as e:
            messages.error(request, f"Error creating category: {str(e)}")
            return render(request, 'manager/category_add.html')
    
    return render(request, 'manager/category_add.html')


@manager_required
def category_edit(request, pk):
    """Edit an existing category"""
    category = get_object_or_404(Category, pk=pk)
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name', category.name).strip()
            description = request.POST.get('description', category.description).strip()
            is_active = request.POST.get('is_active') == 'on'
            
            if not name:
                messages.error(request, "Category name cannot be empty.")
                return render(request, 'manager/category_edit.html', {'category': category})
            
            # Check duplicate name
            if Category.objects.filter(name__iexact=name).exclude(pk=category.pk).exists():
                messages.error(request, f"Another category with name '{name}' already exists.")
                return render(request, 'manager/category_edit.html', {'category': category})
            
            category.name = name
            category.description = description
            category.is_active = is_active
            category.save()
            
            messages.success(request, f"Category '{category.name}' updated successfully!")
            return redirect('manager:categories')
            
        except Exception as e:
            messages.error(request, f"Error updating category: {str(e)}")
    
    context = {'category': category}
    return render(request, 'manager/category_edit.html', context)


@manager_required
def category_delete(request, pk):
    """Delete a category with safety checks"""
    category = get_object_or_404(Category.objects.annotate(product_count=Count('products')), pk=pk)
    
    if request.method == 'POST':
        if category.products.exists():
            messages.error(request, f"Cannot delete category '{category.name}' because it contains {category.products.count()} active product(s). Reassign or delete the products first.")
            return redirect('manager:categories')
            
        category_name = category.name
        category.delete()
        messages.success(request, f"Category '{category_name}' deleted successfully!")
        return redirect('manager:categories')
    
    context = {'category': category}
    return render(request, 'manager/category_confirm_delete.html', context)


# ===== BRAND MANAGEMENT =====

@manager_required
def manager_brands(request):
    """Display list of all brands with product counts"""
    brands = Brand.objects.annotate(product_count=Count('products')).order_by('name')
    context = {'brands': brands}
    return render(request, 'manager/brands.html', context)


@manager_required
def brand_add(request):
    """Create a new brand"""
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            
            if not name:
                messages.error(request, "Brand name is required.")
                return render(request, 'manager/brand_add.html')
            
            if Brand.objects.filter(name__iexact=name).exists():
                messages.error(request, f"A brand with name '{name}' already exists.")
                return render(request, 'manager/brand_add.html')
            
            brand = Brand(name=name, description=description)
            brand.save()
            
            messages.success(request, f"Brand '{name}' created successfully!")
            return redirect('manager:brands')
            
        except Exception as e:
            messages.error(request, f"Error creating brand: {str(e)}")
            return render(request, 'manager/brand_add.html')
    
    return render(request, 'manager/brand_add.html')


@manager_required
def brand_edit(request, pk):
    """Edit an existing brand"""
    brand = get_object_or_404(Brand, pk=pk)
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name', brand.name).strip()
            description = request.POST.get('description', brand.description).strip()
            
            if not name:
                messages.error(request, "Brand name cannot be empty.")
                return render(request, 'manager/brand_edit.html', {'brand': brand})
            
            if Brand.objects.filter(name__iexact=name).exclude(pk=brand.pk).exists():
                messages.error(request, f"Another brand with name '{name}' already exists.")
                return render(request, 'manager/brand_edit.html', {'brand': brand})
            
            brand.name = name
            brand.description = description
            brand.save()
            
            messages.success(request, f"Brand '{brand.name}' updated successfully!")
            return redirect('manager:brands')
            
        except Exception as e:
            messages.error(request, f"Error updating brand: {str(e)}")
    
    context = {'brand': brand}
    return render(request, 'manager/brand_edit.html', context)


@manager_required
def brand_delete(request, pk):
    """Delete a brand"""
    brand = get_object_or_404(Brand.objects.annotate(product_count=Count('products')), pk=pk)
    
    if request.method == 'POST':
        brand_name = brand.name
        brand.delete()
        messages.success(request, f"Brand '{brand_name}' deleted successfully!")
        return redirect('manager:brands')
    
    context = {'brand': brand}
    return render(request, 'manager/brand_confirm_delete.html', context)


# ===== INVENTORY MANAGEMENT =====

@manager_required
def manager_inventory(request):
    """Manage product inventory and stock levels with instant inline update"""
    products = Product.objects.select_related('category', 'brand').all()
    
    # Handle inline stock update
    if request.method == 'POST':
        try:
            product_id = request.POST.get('product_id')
            new_stock = request.POST.get('new_stock')
            
            product = get_object_or_404(Product, id=product_id)
            old_stock = product.stock
            product.stock = max(0, int(new_stock))
            product.save()
            
            messages.success(
                request, 
                f"Stock updated for '{product.name}': {old_stock} → {product.stock} units ({product.stock_status})"
            )
        except Exception as e:
            messages.error(request, f"Error updating stock: {str(e)}")
        
        return redirect('manager:inventory')
    
    # Filtering
    status_filter = request.GET.get('status')
    if status_filter == 'in_stock':
        products = products.filter(stock__gt=10)
    elif status_filter == 'low_stock':
        products = products.filter(stock__gt=0, stock__lte=10)
    elif status_filter == 'out_of_stock':
        products = products.filter(stock=0)
        
    query = request.GET.get('q', '').strip()
    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(category__name__icontains=query) |
            Q(brand__name__icontains=query)
        )
    
    context = {
        'products': products,
        'selected_status': status_filter,
        'query': query,
        'total_inventory': Product.objects.aggregate(total=Sum('stock'))['total'] or 0,
        'low_stock_count': Product.objects.filter(stock__gt=0, stock__lte=10).count(),
        'out_of_stock_count': Product.objects.filter(stock=0).count(),
    }
    return render(request, 'manager/inventory.html', context)


# ===== ORDER MANAGEMENT =====

@manager_required
def manager_orders(request):
    """Display list of all orders with filtering and sorting"""
    orders = Order.objects.select_related('user').prefetch_related('items__product').all()
    
    # Status filter
    status = request.GET.get('status')
    if status and status != 'All Orders':
        orders = orders.filter(status=status)
    
    # Customer / Order Search
    query = request.GET.get('q', '').strip()
    if query:
        if query.isdigit():
            orders = orders.filter(Q(id=int(query)) | Q(user__email__icontains=query) | Q(user__name__icontains=query))
        else:
            orders = orders.filter(Q(user__email__icontains=query) | Q(user__name__icontains=query) | Q(shipping_address__icontains=query))
    
    # Sort by newest first
    orders = orders.order_by('-created_at')
    
    context = {
        'orders': orders,
        'selected_status': status,
        'query': query,
        'status_choices': Order.STATUS_CHOICES,
        'total_orders_count': Order.objects.count(),
        'pending_count': Order.objects.filter(status='Pending').count(),
        'paid_count': Order.objects.filter(status='Paid').count(),
        'shipped_count': Order.objects.filter(status='Shipped').count(),
        'delivered_count': Order.objects.filter(status='Delivered').count(),
    }
    return render(request, 'manager/orders.html', context)


@manager_required
def order_detail(request, pk):
    """Display detailed order information with customer info, items, and status update"""
    order = get_object_or_404(Order.objects.select_related('user').prefetch_related('items__product'), pk=pk)
    
    context = {
        'order': order,
        'order_items': order.items.select_related('product'),
        'status_choices': Order.STATUS_CHOICES,
    }
    return render(request, 'manager/order_detail.html', context)


@manager_required
def update_order_status(request, pk):
    """Update order status via POST"""
    order = get_object_or_404(Order, pk=pk)
    
    if request.method == 'POST':
        try:
            new_status = request.POST.get('status')
            valid_statuses = [choice[0] for choice in Order.STATUS_CHOICES]
            if new_status in valid_statuses:
                old_status = order.status
                order.status = new_status
                order.save()
                messages.success(
                    request,
                    f"Order #{order.id} status updated from '{old_status}' to '{new_status}' successfully!"
                )
            else:
                messages.error(request, "Invalid status selected.")
        except Exception as e:
            messages.error(request, f"Error updating order status: {str(e)}")
            
    # Redirect back to where request originated or order_detail
    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('manager:order_detail', pk=pk)


# ===== SALES REPORTS =====

@manager_required
def sales_reports(request):
    """Display comprehensive sales analytics and reports"""
    stats = get_sales_stats()
    
    # Calculate product sales
    orders = Order.objects.filter(status__in=['Paid', 'Shipped', 'Delivered']).prefetch_related('items__product__category')
    product_sales = {}
    category_sales = {}
    
    for order in orders:
        for item in order.items.all():
            if item.product:
                pid = item.product.id
                if pid not in product_sales:
                    product_sales[pid] = {
                        'product': item.product,
                        'units_sold': 0,
                        'revenue': 0.0,
                    }
                product_sales[pid]['units_sold'] += item.quantity
                product_sales[pid]['revenue'] += float(item.get_subtotal())
                
                # Category sales
                cat_name = item.product.category.name if item.product.category else 'Uncategorized'
                category_sales[cat_name] = category_sales.get(cat_name, 0.0) + float(item.get_subtotal())
    
    # Top 10 products sorted by revenue
    top_products = sorted(
        product_sales.values(),
        key=lambda x: x['revenue'],
        reverse=True
    )[:10]
    
    # Status distribution for Chart.js
    status_distribution = {
        'Pending': Order.objects.filter(status='Pending').count(),
        'Paid': Order.objects.filter(status='Paid').count(),
        'Shipped': Order.objects.filter(status='Shipped').count(),
        'Delivered': Order.objects.filter(status='Delivered').count(),
    }
    
    context = {
        'total_revenue': stats['total_revenue'],
        'total_orders': stats['total_orders'],
        'completed_orders': stats['completed_orders'],
        'pending_orders': stats['pending_orders'],
        'average_order_value': stats['average_order_value'],
        'top_products': top_products,
        'category_sales': category_sales,
        'status_distribution': status_distribution,
    }
    
    return render(request, 'manager/reports.html', context)
