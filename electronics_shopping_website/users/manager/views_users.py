from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum, Q
from django.core.paginator import Paginator
from django.http import JsonResponse

from .decorators import manager_required

User = get_user_model()


@manager_required
def manager_users(request):
    """
    Admin/Manager Customer Management Directory:
    View registered customers, see total orders, total revenue spent, and manage account status.
    """
    queryset = User.objects.filter(is_superuser=False).annotate(
        orders_count=Count('orders', distinct=True),
        total_spent=Sum(
            'orders__total_amount',
            filter=Q(orders__status__in=['Paid', 'Shipped', 'Delivered'])
        )
    ).order_by('-date_joined')

    # 1. Search Query
    query = request.GET.get('q', '').strip()
    if query:
        queryset = queryset.filter(
            Q(email__icontains=query) | Q(name__icontains=query)
        )

    # 2. Status Filter
    status_filter = request.GET.get('status', '').strip()
    if status_filter == 'active':
        queryset = queryset.filter(is_active=True)
    elif status_filter == 'inactive':
        queryset = queryset.filter(is_active=False)
    elif status_filter == 'staff':
        queryset = queryset.filter(is_staff=True)

    # Calculate summary metrics
    total_customers = User.objects.filter(is_superuser=False).count()
    active_customers = User.objects.filter(is_superuser=False, is_active=True).count()
    inactive_customers = User.objects.filter(is_superuser=False, is_active=False).count()
    
    from orders.models import Order
    total_customer_orders = Order.objects.count()

    # Pagination
    paginator = Paginator(queryset, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'users': page_obj,
        'query': query,
        'selected_status': status_filter,
        'total_customers': total_customers,
        'active_customers': active_customers,
        'inactive_customers': inactive_customers,
        'total_customer_orders': total_customer_orders,
    }
    return render(request, 'manager/users.html', context)


@manager_required
def user_toggle_status(request, pk):
    """Toggle customer active/inactive status"""
    user_to_toggle = get_object_or_404(User, pk=pk)

    if user_to_toggle == request.user:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": "You cannot deactivate your own account."}, status=400)
        messages.error(request, "You cannot deactivate your own account.")
        return redirect('manager:users')

    if user_to_toggle.is_superuser:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": "Superadmin status cannot be modified from this view."}, status=400)
        messages.error(request, "Superadmin status cannot be modified from this view.")
        return redirect('manager:users')

    user_to_toggle.is_active = not user_to_toggle.is_active
    user_to_toggle.save()

    status_str = "activated" if user_to_toggle.is_active else "deactivated"
    msg = f"User account '{user_to_toggle.email}' was successfully {status_str}."

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "is_active": user_to_toggle.is_active,
            "message": msg
        })

    messages.success(request, msg)
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('manager:users')


@manager_required
def manager_user_detail(request, pk):
    """Detailed view for a specific registered customer"""
    customer = get_object_or_404(
        User.objects.prefetch_related('addresses', 'orders__items__product'),
        pk=pk
    )
    customer_orders = customer.orders.all().order_by('-created_at')
    
    total_spent = customer_orders.filter(
        status__in=['Paid', 'Shipped', 'Delivered']
    ).aggregate(total=Sum('total_amount'))['total'] or 0.0

    context = {
        'customer': customer,
        'orders': customer_orders,
        'total_spent': total_spent,
        'addresses': customer.addresses.all(),
    }
    return render(request, 'manager/user_detail.html', context)
