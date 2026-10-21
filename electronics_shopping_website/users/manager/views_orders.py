import random
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, F
from django.utils import timezone

from orders.models import Order
from products.models import Product
from .decorators import manager_required


@manager_required
def manager_orders(request):
    """Display list of all orders with filtering and sorting"""
    try:
        from orders.services_lifecycle import run_order_progression_sweep
        run_order_progression_sweep(hours_delay=1, immediate=False)
    except Exception:
        pass

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
        'cancelled_count': Order.objects.filter(status='Cancelled').count(),
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
    """Update order status via POST with automatic stock restoration upon cancellation"""
    order = get_object_or_404(Order, pk=pk)
    
    if request.method == 'POST':
        try:
            new_status = request.POST.get('status')
            valid_statuses = [choice[0] for choice in Order.STATUS_CHOICES]
            if new_status in valid_statuses:
                old_status = order.status
                order.status = new_status

                if new_status == 'Shipped':
                    if not order.shipped_at:
                        order.shipped_at = timezone.now()
                    if not order.tracking_number:
                        order.tracking_number = f"ETX-{random.randint(100000, 999999)}"
                    if not order.carrier_name:
                        order.carrier_name = "BlueDart Express"
                    if not order.estimated_delivery_date:
                        order.estimated_delivery_date = timezone.now().date() + timedelta(days=5)
                elif new_status == 'Delivered':
                    if not order.delivered_at:
                        order.delivered_at = timezone.now()
                    if not order.shipped_at:
                        order.shipped_at = timezone.now()

                order.save()

                # Atomic stock restoration if order was cancelled
                if new_status == 'Cancelled' and old_status != 'Cancelled':
                    for item in order.items.select_related('product').all():
                        if item.product_id:
                            Product.objects.filter(id=item.product_id).update(stock=F('stock') + item.quantity)
                    messages.success(
                        request,
                        f"Order #{order.id} marked as 'Cancelled'. Restored {order.items.count()} product inventory items back to stock!"
                    )
                # Deduct stock back if previously cancelled order is restored
                elif old_status == 'Cancelled' and new_status != 'Cancelled':
                    for item in order.items.select_related('product').all():
                        if item.product_id:
                            Product.objects.filter(id=item.product_id).update(stock=F('stock') - item.quantity)
                    messages.success(
                        request,
                        f"Order #{order.id} status updated from '{old_status}' to '{new_status}' successfully!"
                    )
                else:
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


@manager_required
def trigger_auto_delivery_sweep(request):
    """Manually triggers the automated order progression sweep from manager dashboard"""
    if request.method == 'POST':
        immediate = request.POST.get('immediate') == '1'
        from orders.services_lifecycle import run_order_progression_sweep
        res = run_order_progression_sweep(hours_delay=1, immediate=immediate)
        shipped = res["shipped_count"]
        delivered = res["delivered_count"]
        mode_label = "Demo Immediate Mode" if immediate else "Standard 1-Hour Delay Mode"
        if shipped > 0 or delivered > 0:
            messages.success(
                request,
                f"Auto-Delivery Sweep completed ({mode_label})! {shipped} order(s) moved to Shipped, {delivered} order(s) moved to Delivered."
            )
        else:
            messages.info(
                request,
                f"Auto-Delivery Sweep completed ({mode_label}). No orders currently met the criteria for status advancement."
            )
    return redirect('manager:orders')

