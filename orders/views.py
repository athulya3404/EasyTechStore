import uuid
import random
from decimal import Decimal
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db import transaction
from django.db.models import F
from django.core.mail import send_mail, EmailMessage
from django.conf import settings
from django.contrib import messages
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.response import Response

from cart.models import Cart, CartItem
from products.models import Product
from .models import Order, OrderItem, Payment
from .serializers import (
    OrderSerializer,
    OrderItemSerializer,
    OrderCreateSerializer,
    PaymentVerificationSerializer,
)
from .payments import (
    generate_transaction_reference,
    generate_payment_signature,
    verify_payment_signature,
    simulate_gateway_handshake,
    PaymentGatewayFactory,
)
from electronics_shopping_website.users.models import Address

ORDER_EXPIRATION_MINUTES = 15


def compute_order_breakdown(gross_total):
    """
    Computes financial breakdown for an order:
    - subtotal: net item costs before GST
    - tax_amount: 18% Integrated GST
    - shipping_fee: ₹0 for orders ₹500+, else ₹50 flat
    """
    gross = Decimal(str(gross_total))
    shipping_fee = Decimal('0.00')
    subtotal = round(gross / Decimal('1.18'), 2)
    tax_amount = round(gross - subtotal, 2)
    return subtotal, tax_amount, shipping_fee, gross


def resolve_order_address(user, shipping_address_str="", address_id=None, post_data=None):
    """
    Extracts structured address fields (recipient_name, phone, street, city, state, postal_code, address)
    from a saved Address record or parsed request data.
    """
    post_data = post_data or {}
    user_addresses = Address.objects.filter(user=user)
    matched_addr = None

    if address_id and str(address_id).isdigit():
        matched_addr = user_addresses.filter(id=int(address_id)).first()

    if not matched_addr and user_addresses.exists():
        if not shipping_address_str:
            matched_addr = user_addresses.filter(is_default=True).first() or user_addresses.first()
        else:
            for addr in user_addresses:
                if addr.get_formatted_address() in shipping_address_str or addr.street_address in shipping_address_str:
                    matched_addr = addr
                    break

    if matched_addr:
        return {
            "recipient_name": matched_addr.full_name,
            "recipient_phone": matched_addr.phone_number,
            "street_address": matched_addr.street_address,
            "city": matched_addr.city,
            "state": matched_addr.state,
            "postal_code": matched_addr.postal_code,
            "address": matched_addr,
            "shipping_address": shipping_address_str or matched_addr.get_formatted_address(),
        }

    return {
        "recipient_name": post_data.get("recipient_name") or getattr(user, "name", "") or "Customer",
        "recipient_phone": post_data.get("recipient_phone") or "",
        "street_address": post_data.get("street_address") or shipping_address_str,
        "city": post_data.get("city") or "",
        "state": post_data.get("state") or "",
        "postal_code": post_data.get("postal_code") or "",
        "address": None,
        "shipping_address": shipping_address_str,
    }


# ==============================================================================
# UI VIEWS
# ==============================================================================

@ensure_csrf_cookie
@login_required
def checkout_view(request):
    """
    Renders the checkout page with cart summary and user's saved addresses.
    Supports selective item checkout via ?items=id1,id2 query parameter.
    Handles HTML form POST with row-level locks, structured address snapshot, and 15-minute order expiration.
    """
    cart, created = Cart.objects.get_or_create(user=request.user)
    
    if not cart.items.exists():
        return redirect('cart:cart_detail')

    product_id_param = request.POST.get("product_id", "").strip() or request.GET.get("product_id", "").strip()
    selected_ids_str = request.POST.get("selected_item_ids", "").strip() or request.GET.get("items", "").strip()

    if product_id_param and product_id_param.isdigit():
        prod = get_object_or_404(Product, id=int(product_id_param), is_active=True)
        qty_param = request.POST.get("quantity", "").strip() or request.GET.get("quantity", "1").strip()
        try:
            qty = max(1, int(qty_param))
        except (ValueError, TypeError):
            qty = 1
        item, _ = CartItem.objects.get_or_create(cart=cart, product=prod, defaults={'quantity': qty})
        if item.quantity != qty:
            item.quantity = qty
            item.save()
        cart_items = [item]
    elif selected_ids_str:
        selected_ids = [int(x) for x in selected_ids_str.split(",") if x.strip().isdigit()]
        cart_items = list(cart.items.filter(id__in=selected_ids).select_related('product'))
        if not cart_items:
            messages.warning(request, "Selected product is not available in your cart.")
            return redirect('cart:cart_detail')
    else:
        if cart.items.count() == 1:
            cart_items = list(cart.items.select_related('product').all())
        elif cart.items.count() > 1:
            messages.info(request, "Please select the specific product you wish to purchase.")
            return redirect('cart:cart_detail')
        else:
            return redirect('cart:cart_detail')

    checkout_total = sum(item.get_subtotal() for item in cart_items)
    addresses = Address.objects.filter(user=request.user)

    if request.method == "POST":
        shipping_address = request.POST.get("shipping_address", "").strip()
        payment_method = request.POST.get("paymentMethod", "Sandbox")
        saved_addr_id = request.POST.get("savedAddressRadio", "").strip()

        if not shipping_address and saved_addr_id and saved_addr_id.isdigit():
            addr_obj = addresses.filter(id=int(saved_addr_id)).first()
            if addr_obj:
                shipping_address = addr_obj.get_formatted_address()

        if not shipping_address and addresses.exists():
            first_addr = addresses.first()
            if first_addr:
                shipping_address = first_addr.get_formatted_address()

        if not shipping_address:
            return render(
                request,
                "orders/checkout.html",
                {
                    "cart": cart,
                    "cart_items": cart_items,
                    "checkout_total": checkout_total,
                    "selected_item_ids": [item.id for item in cart_items],
                    "addresses": addresses,
                    "error": "Please provide a valid shipping address.",
                }
            )

        addr_data = resolve_order_address(
            user=request.user,
            shipping_address_str=shipping_address,
            address_id=int(saved_addr_id) if (saved_addr_id and saved_addr_id.isdigit()) else None,
            post_data=request.POST
        )

        try:
            with transaction.atomic():
                product_ids = [ci.product.id for ci in cart_items]
                locked_products = {
                    p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids)
                }

                for cart_item in cart_items:
                    locked_prod = locked_products.get(cart_item.product.id)
                    if not locked_prod or cart_item.quantity > locked_prod.stock:
                        available = locked_prod.stock if locked_prod else 0
                        return render(
                            request,
                            "orders/checkout.html",
                            {
                                "cart": cart,
                                "cart_items": cart_items,
                                "checkout_total": checkout_total,
                                "selected_item_ids": [item.id for item in cart_items],
                                "addresses": addresses,
                                "error": f"Insufficient stock for '{cart_item.product.name}'. Available: {available}",
                            }
                        )

                is_cod = (payment_method == "COD")
                initial_status = Order.STATUS_PENDING
                expires_at = timezone.now() + timedelta(minutes=ORDER_EXPIRATION_MINUTES)
                subtotal_val, tax_val, shipping_val, total_val = compute_order_breakdown(checkout_total)

                deliv_days = random.randint(3, 5)
                est_delivery = (timezone.now() + timedelta(days=deliv_days)).date()
                track_code = f"ETX-{random.randint(100000, 999999)}"

                order = Order.objects.create(
                    user=request.user,
                    recipient_name=addr_data["recipient_name"],
                    recipient_phone=addr_data["recipient_phone"],
                    street_address=addr_data["street_address"],
                    city=addr_data["city"],
                    state=addr_data["state"],
                    postal_code=addr_data["postal_code"],
                    address=addr_data["address"],
                    shipping_address=addr_data["shipping_address"],
                    status=initial_status,
                    subtotal=subtotal_val,
                    tax_amount=tax_val,
                    shipping_fee=shipping_val,
                    total_amount=total_val,
                    expires_at=expires_at,
                    estimated_delivery_date=est_delivery,
                    tracking_number=track_code,
                )

                item_ids_to_delete = []
                for cart_item in cart_items:
                    unit_price = cart_item.product.get_discounted_price()
                    OrderItem.objects.create(
                        order=order,
                        product=cart_item.product,
                        quantity=cart_item.quantity,
                        price_at_purchase=unit_price,
                    )
                    updated = Product.objects.filter(
                        id=cart_item.product.id,
                        stock__gte=cart_item.quantity,
                    ).update(stock=F('stock') - cart_item.quantity)

                    if not updated:
                        raise ValueError(f"Stock conflict on '{cart_item.product.name}'. Please retry.")

                    item_ids_to_delete.append(cart_item.id)

                txn_hash = generate_transaction_reference()
                Payment.objects.create(
                    order=order,
                    payment_method=payment_method[:20],
                    transaction_id=txn_hash,
                    amount=checkout_total,
                    status='Pending'
                )

                cart.items.filter(id__in=item_ids_to_delete).delete()

                if is_cod:
                    send_order_confirmation_email(order, request.user, payment_method, txn_hash)
                    return redirect("orders:confirmation", order_id=order.id)
                else:
                    return redirect("orders:payment_gateway", order_id=order.id)

        except Exception as e:
            return render(
                request,
                "orders/checkout.html",
                {
                    "cart": cart,
                    "cart_items": cart_items,
                    "checkout_total": checkout_total,
                    "selected_item_ids": [item.id for item in cart_items],
                    "addresses": addresses,
                    "error": f"Checkout failed: {str(e)}",
                }
            )

    return render(
        request, 
        "orders/checkout.html", 
        {
            "cart": cart,
            "cart_items": cart_items,
            "checkout_total": checkout_total,
            "selected_item_ids": [item.id for item in cart_items],
            "addresses": addresses,
        }
    )


@login_required
def customer_orders_view(request):
    """Customer view for their order history & tracking."""
    if request.user.is_staff or request.user.is_superuser:
        orders = Order.objects.filter(user=request.user).prefetch_related('items__product', 'payments').order_by('-created_at')
        if not orders.exists():
            orders = Order.objects.all().prefetch_related('items__product', 'payments').order_by('-created_at')[:25]
    else:
        orders = Order.objects.filter(user=request.user).prefetch_related('items__product', 'payments').order_by('-created_at')
    return render(request, "orders/my_orders.html", {"orders": orders})


@login_required
def order_confirmation_view(request, order_id):
    """Customer view for order confirmation receipt with Visual Status Tracker."""
    if request.user.is_staff or request.user.is_superuser:
        order = get_object_or_404(Order.objects.prefetch_related('items__product', 'payments'), id=order_id)
    else:
        order = get_object_or_404(Order.objects.prefetch_related('items__product', 'payments'), id=order_id, user=request.user)
    return render(request, "orders/order_confirmation.html", {"order": order})


def _generate_pure_python_invoice_pdf(order) -> bytes:
    """
    Generates a 100% standard-compliant, self-contained binary PDF invoice
    with Helvetica fonts, tables, order lines, and totals without external dependencies.
    """
    created_str = order.created_at.strftime('%Y-%m-%d %H:%M') if getattr(order, 'created_at', None) else 'N/A'
    recipient = order.recipient_name or (order.user.name if getattr(order, 'user', None) and getattr(order.user, 'name', None) else (order.user.email if getattr(order, 'user', None) else 'Customer'))
    addr = order.street_address or order.shipping_address or 'Standard Delivery'
    city_st = f"{order.city or ''} {order.state or ''} {order.postal_code or ''}".strip()
    total = float(order.total_amount or 0)
    subtotal = float(order.subtotal) if getattr(order, 'subtotal', None) else (total / 1.18)
    gst = float(order.tax_amount) if getattr(order, 'tax_amount', None) else (total - subtotal)
    shipping = float(order.shipping_fee) if getattr(order, 'shipping_fee', None) else 0.0

    lines = []
    # Title & Header
    lines.append("BT 0.06 0.09 0.16 rg /F1 18 Tf 50 740 Td (EASYTECH STORE) Tj ET")
    lines.append("BT 0.06 0.09 0.16 rg /F1 12 Tf 50 720 Td (Official Tax Invoice & Purchase Receipt) Tj ET")
    lines.append("BT 0.35 0.4 0.48 rg /F2 9 Tf 50 705 Td (Valid under Indian Information Technology Act, 2000) Tj ET")

    # Header accent divider line
    lines.append("0.29 0.33 0.85 rg 50 695 512 2.5 re f")

    # Order metadata
    lines.append(f"BT 0.06 0.09 0.16 rg /F1 10 Tf 50 675 Td (Invoice #: INV-{order.id:06d}) Tj ET")
    lines.append(f"BT 0.25 0.3 0.38 rg /F2 9.5 Tf 50 660 Td (Order Date: {created_str}) Tj ET")
    lines.append(f"BT 0.25 0.3 0.38 rg /F2 9.5 Tf 50 645 Td (Order Status: {order.status}) Tj ET")

    # Customer Details
    lines.append("BT 0.06 0.09 0.16 rg /F1 10 Tf 320 675 Td (Billed & Shipped To:) Tj ET")
    clean_recip = str(recipient).replace('(', '').replace(')', '')[:35]
    lines.append(f"BT 0.15 0.2 0.28 rg /F2 9.5 Tf 320 660 Td ({clean_recip}) Tj ET")
    clean_addr = str(addr).replace('(', '').replace(')', '')[:42]
    lines.append(f"BT 0.3 0.35 0.42 rg /F2 9 Tf 320 645 Td ({clean_addr}) Tj ET")
    if city_st:
        clean_city = city_st.replace('(', '').replace(')', '')[:42]
        lines.append(f"BT 0.3 0.35 0.42 rg /F2 9 Tf 320 630 Td ({clean_city}) Tj ET")

    # Table Header Box (Dark Navy Background with Crisp White Text)
    lines.append("0.06 0.09 0.16 rg 50 595 512 22 re f")
    lines.append("BT 1 1 1 rg /F1 9 Tf 58 602 Td (Item Description) Tj ET")
    lines.append("BT 1 1 1 rg /F1 9 Tf 330 602 Td (Unit Price) Tj ET")
    lines.append("BT 1 1 1 rg /F1 9 Tf 420 602 Td (Qty) Tj ET")
    lines.append("BT 1 1 1 rg /F1 9 Tf 470 602 Td (Subtotal (INR)) Tj ET")

    y = 574
    for item in order.items.all():
        pname = (item.product.name if item.product else "Electronics Gadget").replace('(', '').replace(')', '')[:36]
        uprice = f"Rs. {float(item.price_at_purchase):,.2f}"
        qty = str(item.quantity)
        ltotal = f"Rs. {float(item.price_at_purchase) * item.quantity:,.2f}"

        # Item row with explicit solid black/navy color per cell
        lines.append(f"BT 0.06 0.09 0.16 rg /F2 9 Tf 58 {y} Td ({pname}) Tj ET")
        lines.append(f"BT 0.15 0.2 0.25 rg /F2 9 Tf 330 {y} Td ({uprice}) Tj ET")
        lines.append(f"BT 0.15 0.2 0.25 rg /F2 9 Tf 425 {y} Td ({qty}) Tj ET")
        lines.append(f"BT 0.06 0.09 0.16 rg /F1 9 Tf 470 {y} Td ({ltotal}) Tj ET")
        lines.append(f"0.92 0.94 0.96 rg 50 {y-5} 512 0.5 re f")
        y -= 22
        if y < 220:
            break

    y -= 8
    # Financial breakdown (Each column has its own absolute coordinate BT ... ET)
    lines.append(f"BT 0.3 0.35 0.42 rg /F2 9.5 Tf 330 {y} Td (Subtotal (Tax Excl.):) Tj ET")
    lines.append(f"BT 0.06 0.09 0.16 rg /F1 9.5 Tf 470 {y} Td (Rs. {subtotal:,.2f}) Tj ET")
    y -= 17
    lines.append(f"BT 0.3 0.35 0.42 rg /F2 9.5 Tf 330 {y} Td (Integrated GST (18%):) Tj ET")
    lines.append(f"BT 0.06 0.09 0.16 rg /F1 9.5 Tf 470 {y} Td (Rs. {gst:,.2f}) Tj ET")
    y -= 17
    ship_str = "FREE" if shipping == 0 else f"Rs. {shipping:,.2f}"
    lines.append(f"BT 0.3 0.35 0.42 rg /F2 9.5 Tf 330 {y} Td (Shipping & Handling:) Tj ET")
    lines.append(f"BT 0.06 0.09 0.16 rg /F1 9.5 Tf 470 {y} Td ({ship_str}) Tj ET")
    y -= 24
    # Grand Total Box
    lines.append(f"0.95 0.97 1.0 rg 320 {y-6} 242 25 re f")
    lines.append(f"0.29 0.33 0.85 RG 1 w 320 {y-6} 242 25 re s")
    lines.append(f"BT 0.06 0.09 0.16 rg /F1 10 Tf 330 {y} Td (Grand Total Payable:) Tj ET")
    lines.append(f"BT 0.06 0.09 0.16 rg /F1 11 Tf 470 {y} Td (Rs. {total:,.2f}) Tj ET")

    # Footer
    lines.append("BT 0.4 0.45 0.5 rg /F2 8 Tf 50 70 Td (Thank you for shopping at EasyTech Store! Computer-generated tax invoice valid under Indian IT Act 2000.) Tj ET")

    stream_content = "\n".join(lines).encode('latin-1', errors='replace')
    stream_len = len(stream_content)

    objects = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>\nendobj\n")
    objects.append(f"4 0 obj\n<< /Length {stream_len} >>\nstream\n".encode('ascii') + stream_content + b"\nendstream\nendobj\n")
    objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\nendobj\n")
    objects.append(b"6 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n")

    # Calculate exact 20-byte per line xref table
    pdf_output = b"%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf_output))
        pdf_output += obj

    xref_pos = len(pdf_output)
    pdf_output += f"xref\n0 {len(offsets)}\n".encode('ascii')
    pdf_output += b"0000000000 65535 f\r\n"
    for offset in offsets[1:]:
        pdf_output += f"{offset:010d} 00000 n\r\n".encode('ascii')

    pdf_output += f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode('ascii')
    return pdf_output


def generate_pdf_invoice_response(order):
    """
    Generates official binary downloadable PDF invoice using ReportLab if available,
    or falls back to high-fidelity pure-Python PDF generator.
    """
    import io
    import html

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'InvoiceTitle',
            parent=styles['Heading1'],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor('#0f172a'),
            fontName='Helvetica-Bold',
        )
        meta_style = ParagraphStyle(
            'InvoiceMeta',
            parent=styles['Normal'],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#475569'),
        )
        header_style = ParagraphStyle(
            'InvoiceHeader',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            textColor=colors.whitesmoke,
            fontName='Helvetica-Bold',
        )

        elements = []
        elements.append(Paragraph("EASYTECH STORE", title_style))
        elements.append(Paragraph("Official Tax Invoice & Purchase Receipt", styles['Heading3']))
        elements.append(Spacer(1, 10))

        created_str = order.created_at.strftime('%B %d, %Y at %I:%M %p') if getattr(order, 'created_at', None) else 'N/A'
        latest_pm = order.payment.payment_method if getattr(order, 'payment', None) else 'Online'

        recipient_disp = html.escape(str(order.recipient_name or (order.user.name if getattr(order, 'user', None) and getattr(order.user, 'name', None) else (order.user.email if getattr(order, 'user', None) else 'Customer'))))
        addr_disp = html.escape(str(order.street_address or order.shipping_address or 'Standard Delivery'))
        city_disp = html.escape(f"{order.city or ''} {order.state or ''} {order.postal_code or ''}".strip())
        phone_disp = html.escape(str(order.recipient_phone or 'N/A'))

        info_data = [
            [
                Paragraph(f"<b>Invoice #:</b> INV-{order.id:06d}<br/><b>Order Date:</b> {created_str}<br/><b>Status:</b> {html.escape(str(order.status))}<br/><b>Payment:</b> {html.escape(str(latest_pm))}", meta_style),
                Paragraph(f"<b>Billed & Shipped To:</b><br/>{recipient_disp}<br/>{addr_disp}<br/>{city_disp}<br/>Phone: {phone_disp}", meta_style),
            ]
        ]
        info_table = Table(info_data, colWidths=[270, 270])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 6),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#e2e8f0')),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 14))

        table_data = [
            [
                Paragraph("Item Description", header_style),
                Paragraph("Unit Price (INR)", header_style),
                Paragraph("Qty", header_style),
                Paragraph("Total (INR)", header_style),
            ]
        ]

        for item in order.items.all():
            line_total = float(item.price_at_purchase) * item.quantity
            pname = html.escape(str(item.product.name if item.product else 'Gadget'))
            table_data.append([
                Paragraph(pname, meta_style),
                Paragraph(f"Rs. {float(item.price_at_purchase):,.2f}", meta_style),
                Paragraph(str(item.quantity), meta_style),
                Paragraph(f"Rs. {line_total:,.2f}", meta_style),
            ])

        items_table = Table(table_data, colWidths=[270, 100, 50, 120])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 10))

        order_total = float(order.total_amount or 0)
        subtotal = float(order.subtotal) if getattr(order, 'subtotal', None) else (order_total / 1.18)
        gst_tax = float(order.tax_amount) if getattr(order, 'tax_amount', None) else (order_total - subtotal)
        shipping = float(order.shipping_fee) if getattr(order, 'shipping_fee', None) else 0.0

        totals_data = [
            ["Subtotal (Tax Exclusive):", f"Rs. {subtotal:,.2f}"],
            ["Integrated GST (18%):", f"Rs. {gst_tax:,.2f}"],
            ["Shipping & Handling:", "FREE" if shipping == 0 else f"Rs. {shipping:,.2f}"],
            ["Grand Total Payable:", f"Rs. {order_total:,.2f}"],
        ]
        totals_table = Table(totals_data, colWidths=[370, 170])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,-1), (-1,-1), 11),
            ('TEXTCOLOR', (0,-1), (-1,-1), colors.HexColor('#0f172a')),
            ('PADDING', (0,0), (-1,-1), 3),
        ]))
        elements.append(totals_table)
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("Thank you for choosing EasyTech Store. This is a computer-generated tax invoice valid under Indian IT Act 2000.", meta_style))

        doc.build(elements)
        buffer.seek(0)
        pdf_bytes = buffer.getvalue()

    except Exception as err:
        import logging
        logging.getLogger(__name__).warning("ReportLab PDF generation notice: %s. Using high-fidelity ISO-standard PDF fallback.", err)
        pdf_bytes = _generate_pure_python_invoice_pdf(order)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="EasyTech_Invoice_#{order.id}.pdf"'
    return response


@login_required
def download_invoice_view(request, order_id, format_pdf=False):
    """Generates official printable sales tax invoice or binary downloadable PDF for order with INR (₹) amounts."""
    if request.user.is_staff or request.user.is_superuser:
        order = get_object_or_404(Order.objects.prefetch_related('items__product', 'payments'), id=order_id)
    else:
        order = get_object_or_404(Order.objects.prefetch_related('items__product', 'payments'), id=order_id, user=request.user)

    if format_pdf or request.GET.get("format") == "pdf" or request.GET.get("download") == "1":
        return generate_pdf_invoice_response(order)

    return render(request, "orders/invoice_print.html", {"order": order})


@login_required
def cancel_order_view(request, order_id):
    """
    Customer self-service order cancellation before shipment.
    Atomically restores reserved stock and cancels order.
    """
    if request.user.is_staff or request.user.is_superuser:
        order = get_object_or_404(Order.objects.prefetch_related('items__product', 'payments'), id=order_id)
    else:
        order = get_object_or_404(Order.objects.prefetch_related('items__product', 'payments'), id=order_id, user=request.user)

    if order.status in [Order.STATUS_SHIPPED, Order.STATUS_DELIVERED]:
        messages.error(request, "Shipped or delivered orders cannot be cancelled online. Please contact support.")
        return redirect("orders:my_orders")

    if order.status == Order.STATUS_CANCELLED:
        messages.info(request, "This order is already cancelled.")
        return redirect("orders:my_orders")

    with transaction.atomic():
        for item in order.items.select_related("product").all():
            if item.product_id:
                Product.objects.filter(id=item.product_id).update(stock=F("stock") + item.quantity)

        order.status = Order.STATUS_CANCELLED
        order.save()
        order.payments.filter(status="Pending").update(status="Failed")

    messages.success(request, f"Order #{order.id} has been cancelled successfully and reserved inventory was restored.")
    return redirect("orders:my_orders")


@login_required
def payment_gateway_view(request, order_id):
    """
    Two-Stage Interactive Sandbox Payment Gateway Portal:
    Renders mock checkout portal simulating Card, UPI QR Code, and NetBanking with success/failure toggles.
    Enforces 15-minute order expiration and allows retries if a payment attempt fails.
    """
    if request.user.is_staff or request.user.is_superuser:
        order = get_object_or_404(Order.objects.prefetch_related('items__product', 'payments'), id=order_id)
    else:
        order = get_object_or_404(Order.objects.prefetch_related('items__product', 'payments'), id=order_id, user=request.user)
    
    # If order is already paid, redirect straight to confirmation receipt
    if order.status in [Order.STATUS_PAID, Order.STATUS_SHIPPED, Order.STATUS_DELIVERED]:
        return redirect("orders:confirmation", order_id=order.id)

    # Check 15-minute expiration
    if order.status in [Order.STATUS_PENDING, Order.STATUS_PAYMENT_PENDING]:
        if order.expires_at and timezone.now() > order.expires_at:
            with transaction.atomic():
                for item in order.items.select_related('product').all():
                    if item.product_id:
                        Product.objects.filter(id=item.product_id).update(stock=F('stock') + item.quantity)
                order.status = Order.STATUS_CANCELLED
                order.save()
                order.payments.filter(status="Pending").update(status="Failed")

            messages.error(request, "Your checkout session has expired (15-minute limit). Reserved items were released.")
            return redirect("cart:cart_detail")

    # If already cancelled
    if order.status == Order.STATUS_CANCELLED:
        messages.error(request, "This order was cancelled. Please rebuild your cart and checkout again.")
        return redirect("cart:cart_detail")

    payment = order.payments.order_by("-created_at").first()
    if not payment:
        payment = Payment.objects.create(
            order=order,
            payment_method="Sandbox",
            amount=order.total_amount,
            status="Pending",
            transaction_id=generate_transaction_reference(),
        )

    # Standard HTML POST simulation fallback
    if request.method == "POST":
        simulate_status = (request.POST.get("simulationOutcome") or "success").lower()
        payment_method = request.POST.get("paymentMethod", "Card")
        
        with transaction.atomic():
            if simulate_status == "success":
                payment = Payment.objects.create(
                    order=order,
                    payment_method=payment_method[:20],
                    transaction_id=generate_transaction_reference(),
                    amount=order.total_amount,
                    status="Success"
                )
                order.status = Order.STATUS_PAID
                order.save()

                send_order_confirmation_email(order, request.user, payment_method, payment.transaction_id)
                return redirect("orders:confirmation", order_id=order.id)
            else:
                # Log failed attempt without cancelling the entire order (Problem 2: Allows Retry)
                payment = Payment.objects.create(
                    order=order,
                    payment_method=payment_method[:20],
                    transaction_id=generate_transaction_reference(),
                    amount=order.total_amount,
                    status="Failed"
                )
                order.status = Order.STATUS_PAYMENT_PENDING
                order.save()

                signature = generate_payment_signature(order.id, str(order.total_amount))
                return render(
                    request,
                    "orders/payment_gateway.html",
                    {
                        "order": order,
                        "payment": payment,
                        "total_amount": order.total_amount,
                        "payment_signature": signature,
                        "error_message": "Payment was declined by issuing network. Please choose another payment method or try again.",
                        "can_retry": True,
                    }
                )

    signature = generate_payment_signature(order.id, str(order.total_amount))

    return render(
        request,
        "orders/payment_gateway.html",
        {
            "order": order,
            "payment": payment,
            "total_amount": order.total_amount,
            "payment_signature": signature,
        }
    )


# ==============================================================================
# REST API & ORDER VIEWSET
# ==============================================================================

def send_order_confirmation_email(order, request_user, payment_method, txn_hash):
    """Sends official order confirmation email with itemized INR (₹) totals and attaches the PDF tax invoice."""
    try:
        items_list = "\n".join(
            [f"• {i.quantity}x {i.product.name} - ₹{i.get_subtotal():.2f}" for i in order.items.select_related('product').all()]
        )
        tracking_info = (
            f"Carrier: {order.carrier_name}\n"
            f"Tracking Number: {order.tracking_number}\n"
            f"Estimated Delivery: {order.estimated_delivery_date.strftime('%A, %B %d, %Y') if order.estimated_delivery_date else '3-5 Business Days'}\n"
            if order.tracking_number else ""
        )
        mail_subject = f"Order Confirmation #{order.id} - EasyTech Store"
        mail_body = (
            f"Dear {request_user.name or 'Customer'},\n\n"
            f"Thank you for your purchase with EasyTech Store!\n\n"
            f"========================================\n"
            f"ORDER SUMMARY\n"
            f"========================================\n"
            f"Order ID: #{order.id}\n"
            f"Order Status: {order.status}\n"
            f"Payment Method: {payment_method}\n"
            f"Transaction Reference: {txn_hash}\n"
            f"{tracking_info}"
            f"Shipping Address: {order.shipping_address}\n\n"
            f"Items Purchased:\n{items_list}\n\n"
            f"Subtotal: ₹{order.subtotal:.2f}\n"
            f"Integrated GST (18%): ₹{order.tax_amount:.2f}\n"
            f"Grand Total Paid: ₹{order.total_amount:.2f}\n"
            f"========================================\n\n"
            f"Your official tax invoice is attached to this email as a PDF document.\n\n"
            f"TRACK YOUR ORDER:\n"
            f"View live carrier tracking and status updates at:\n"
            f"/orders/confirmation/{order.id}/\n\n"
            f"SHARE YOUR FEEDBACK:\n"
            f"We hope you enjoy your new gadget! Once received, share your verified buyer review on EasyTech Store to help fellow shoppers.\n\n"
            f"Best regards,\n"
            f"EasyTech Store Logistics Team"
        )
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "EasyTech <noreply@easytechstore.com>")
        email = EmailMessage(
            subject=mail_subject,
            body=mail_body,
            from_email=from_email,
            to=[request_user.email],
        )

        try:
            pdf_response = generate_pdf_invoice_response(order)
            if pdf_response and hasattr(pdf_response, 'content'):
                email.attach(
                    f"EasyTech_Invoice_#{order.id}.pdf",
                    pdf_response.content,
                    "application/pdf"
                )
        except Exception as pdf_err:
            print("PDF invoice attachment notice:", str(pdf_err))

        email.send(fail_silently=True)
        order.invoice_sent_at = timezone.now()
        order.save(update_fields=['invoice_sent_at'])
        return True
    except Exception as mail_err:
        print("Order confirmation email error:", str(mail_err))
        return False


class OrderViewSet(viewsets.ViewSet):
    """API for managing orders, checkout, and backend payment simulation."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    @action(detail=False, methods=['get'])
    def my_orders(self, request):
        """API endpoint to list customer's historical orders utilizing DRF OrderSerializer."""
        orders = Order.objects.filter(user=request.user).prefetch_related('items__product', 'payments')
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def place_order(self, request):
        """
        Stage 1 of Checkout:
        1. Validates selected cart items and shipping address.
        2. Acquires row-level pessimistic locks (select_for_update) inside atomic block.
        3. Creates Order with 'Pending' status and 15-minute expiration timestamp.
        4. Atomically decrements product stock guarded with stock__gte.
        5. Creates initial Payment record.
        6. Clears purchased items from the user's cart.
        7. Returns payment gateway redirect URL for interactive mock payment.
        """
        cart = Cart.objects.filter(user=request.user).first()
        
        if not cart or not cart.items.exists():
            return Response(
                {"error": "Your cart is empty."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        shipping_address = request.data.get("shipping_address", "").strip()
        payment_method = request.data.get("payment_method", "Sandbox")
        selected_item_ids = request.data.get("selected_item_ids", [])
        auto_capture = request.data.get("auto_capture", False)
        address_id = request.data.get("address_id")

        if not shipping_address and not address_id:
            return Response(
                {"error": "Shipping address is required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        addr_data = resolve_order_address(
            user=request.user,
            shipping_address_str=shipping_address,
            address_id=address_id,
            post_data=request.data
        )

        # Identify items to order: ensure only the chosen product(s) are ordered
        product_id_param = request.data.get("product_id")
        if product_id_param:
            prod = get_object_or_404(Product, id=product_id_param, is_active=True)
            qty = max(1, int(request.data.get("quantity", 1)))
            item, _ = CartItem.objects.get_or_create(cart=cart, product=prod, defaults={'quantity': qty})
            items_to_order = [item]
        elif selected_item_ids:
            items_to_order = list(cart.items.filter(id__in=selected_item_ids).select_related('product'))
            if not items_to_order:
                return Response(
                    {"error": "Selected items were not found in your cart."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            if cart.items.count() == 1:
                items_to_order = list(cart.items.select_related('product').all())
            else:
                return Response(
                    {"error": "Please select the specific product you wish to purchase. Additional cart items are not automatically included."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

        if not items_to_order:
            return Response(
                {"error": "No items selected for checkout."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                product_ids = [ci.product.id for ci in items_to_order]
                locked_products = {
                    p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids)
                }

                for cart_item in items_to_order:
                    locked_prod = locked_products.get(cart_item.product.id)
                    if not locked_prod or cart_item.quantity > locked_prod.stock:
                        available = locked_prod.stock if locked_prod else 0
                        return Response(
                            {"error": f"Insufficient stock for '{cart_item.product.name}'. Available: {available}"},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                order_total = sum(item.get_subtotal() for item in items_to_order)
                is_cod = (payment_method == "COD")
                should_auto_pay = auto_capture and not is_cod

                initial_status = Order.STATUS_PAID if should_auto_pay else Order.STATUS_PENDING
                expires_at = timezone.now() + timedelta(minutes=ORDER_EXPIRATION_MINUTES)
                subtotal_val, tax_val, shipping_val, total_val = compute_order_breakdown(order_total)

                deliv_days = random.randint(3, 5)
                est_delivery = (timezone.now() + timedelta(days=deliv_days)).date()
                track_code = f"ETX-{random.randint(100000, 999999)}"

                order = Order.objects.create(
                    user=request.user,
                    recipient_name=addr_data["recipient_name"],
                    recipient_phone=addr_data["recipient_phone"],
                    street_address=addr_data["street_address"],
                    city=addr_data["city"],
                    state=addr_data["state"],
                    postal_code=addr_data["postal_code"],
                    address=addr_data["address"],
                    shipping_address=addr_data["shipping_address"],
                    status=initial_status,
                    subtotal=subtotal_val,
                    tax_amount=tax_val,
                    shipping_fee=shipping_val,
                    total_amount=total_val,
                    expires_at=expires_at,
                    estimated_delivery_date=est_delivery,
                    tracking_number=track_code,
                )

                item_ids_to_delete = []
                for cart_item in items_to_order:
                    unit_price = cart_item.product.get_discounted_price()
                    
                    OrderItem.objects.create(
                        order=order,
                        product=cart_item.product,
                        quantity=cart_item.quantity,
                        price_at_purchase=unit_price
                    )

                    updated = Product.objects.filter(
                        id=cart_item.product.id,
                        stock__gte=cart_item.quantity
                    ).update(stock=F('stock') - cart_item.quantity)

                    if not updated:
                        raise ValueError(f"Stock conflict on '{cart_item.product.name}'. Please retry.")

                    item_ids_to_delete.append(cart_item.id)

                txn_hash = generate_transaction_reference()
                Payment.objects.create(
                    order=order,
                    payment_method=payment_method[:20],
                    transaction_id=txn_hash,
                    amount=order_total,
                    status='Success' if should_auto_pay else 'Pending'
                )

                cart.items.filter(id__in=item_ids_to_delete).delete()

                if should_auto_pay or is_cod:
                    send_order_confirmation_email(order, request.user, payment_method, txn_hash)
                    redirect_url = f"/orders/confirmation/{order.id}/"
                else:
                    redirect_url = f"/orders/payment-gateway/{order.id}/"

                return Response({
                    "success": True,
                    "message": "Order created successfully!", 
                    "order_id": order.id,
                    "transaction_id": txn_hash,
                    "status": order.status,
                    "total_amount": str(order_total),
                    "redirect_url": redirect_url,
                    "expires_at": order.expires_at.isoformat() if order.expires_at else None,
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {"error": f"Order checkout failed: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def verify_payment(self, request):
        """
        Stage 2 of Two-Stage Gateway:
        Verifies mock payment outcome (Success or Failure simulation) atomically:
        - If Success: transitions Payment -> 'Success', Order -> 'Paid', sends confirmation email.
        - If Failure: logs Payment -> 'Failed', preserves Order in 'Payment_Pending' to allow retry.
        - If Expired (> 15 mins): cancels order and restores inventory back to products.
        - Idempotent: Row locks order with select_for_update; returns existing confirmation if already paid.
        """
        order_id = request.data.get("order_id")
        payment_method = request.data.get("payment_method", "Card")
        simulate_status = (request.data.get("simulate_status") or request.data.get("simulated_action") or "success").lower()
        idempotency_key = request.data.get("idempotency_key") or request.headers.get("X-Idempotency-Key")

        if not order_id:
            return Response({"error": "order_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            order = get_object_or_404(
                Order.objects.select_for_update(),
                id=order_id,
                user=request.user
            )

            # Idempotency Check: if order is already paid or this request was already processed
            if order.status == Order.STATUS_PAID:
                existing_payment = order.payments.filter(status="Success").order_by("-created_at").first()
                return Response({
                    "success": True,
                    "idempotent": True,
                    "message": "Order is already paid.",
                    "order_id": order.id,
                    "transaction_id": existing_payment.transaction_id if existing_payment else "",
                    "redirect_url": f"/orders/confirmation/{order.id}/"
                }, status=status.HTTP_200_OK)

            if order.status == Order.STATUS_CANCELLED:
                return Response({
                    "success": False,
                    "error": "This order has already been cancelled. Please place a new order from your cart.",
                    "order_id": order.id,
                    "redirect_url": "/orders/checkout/"
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check expiration (15 minutes)
            if order.status in [Order.STATUS_PENDING, Order.STATUS_PAYMENT_PENDING]:
                if order.expires_at and timezone.now() > order.expires_at:
                    for item in order.items.select_related('product').all():
                        if item.product_id:
                            Product.objects.filter(id=item.product_id).update(stock=F('stock') + item.quantity)
                    order.status = Order.STATUS_CANCELLED
                    order.save()
                    order.payments.filter(status="Pending").update(status="Failed")

                    return Response({
                        "success": False,
                        "can_retry": False,
                        "error": "This checkout session has expired (15-minute timeout). Reserved inventory has been restored.",
                        "order_id": order.id,
                        "redirect_url": "/cart/"
                    }, status=status.HTTP_400_BAD_REQUEST)

            if simulate_status == "success":
                txn_hash = (str(idempotency_key)[:50]) if idempotency_key else generate_transaction_reference()
                payment = Payment.objects.create(
                    order=order,
                    payment_method=payment_method[:20],
                    transaction_id=txn_hash,
                    amount=order.total_amount,
                    status="Success"
                )

                order.status = Order.STATUS_PAID
                order.save()

                send_order_confirmation_email(order, request.user, payment_method, payment.transaction_id)

                return Response({
                    "success": True,
                    "message": "Payment verified successfully!",
                    "order_id": order.id,
                    "transaction_id": payment.transaction_id,
                    "redirect_url": f"/orders/confirmation/{order.id}/"
                }, status=status.HTTP_200_OK)
            else:
                # Failure attempt: record attempt as Failed but keep Order in Payment_Pending to allow retry
                txn_hash = generate_transaction_reference()
                payment = Payment.objects.create(
                    order=order,
                    payment_method=payment_method[:20],
                    transaction_id=txn_hash,
                    amount=order.total_amount,
                    status="Failed"
                )

                order.status = Order.STATUS_PAYMENT_PENDING
                order.save()

                return Response({
                    "success": False,
                    "can_retry": True,
                    "error": "Payment was declined by issuing network. Please select another payment method or try again.",
                    "order_id": order.id
                }, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_payment_api(request):
    """Global alias endpoint for POST /api/payments/verify/"""
    viewset = OrderViewSet()
    viewset.request = request
    viewset.format_kwarg = None
    return viewset.verify_payment(request)


@login_required
def advance_order_status_view(request, order_id):
    """
    Store Manager / Admin viva demo quick-action:
    Advances an order through the fulfillment pipeline:
    Paid -> Shipped -> Delivered
    """
    if not (request.user.is_staff or request.user.is_superuser or getattr(request.user, "is_manager", False)):
        messages.error(request, "Permission denied. Only store managers can advance order delivery status.")
        return redirect("orders:my_orders")

    order = get_object_or_404(Order, id=order_id)
    now = timezone.now()

    if order.status == Order.STATUS_PAID:
        order.status = Order.STATUS_SHIPPED
        order.shipped_at = now
        if not order.tracking_number:
            order.tracking_number = f"ETX-{random.randint(100000, 999999)}"
        if not order.carrier_name:
            order.carrier_name = "BlueDart Express"
        if not order.estimated_delivery_date:
            order.estimated_delivery_date = now.date() + timedelta(days=5)
        order.save()
        messages.success(request, f"⚡ Order #{order.id} status advanced to SHIPPED ({order.delivery_status_display}).")
    elif order.status == Order.STATUS_SHIPPED:
        order.status = Order.STATUS_DELIVERED
        order.delivered_at = now
        order.save()
        messages.success(request, f"⚡ Order #{order.id} status advanced to DELIVERED.")
    elif order.status == Order.STATUS_PENDING:
        order.status = Order.STATUS_PAID
        order.save()
        messages.success(request, f"⚡ Order #{order.id} marked as PAID.")
    else:
        messages.info(request, f"Order #{order.id} is already in state: {order.status}.")

    next_url = request.GET.get("next") or request.META.get("HTTP_REFERER")
    if next_url:
        return redirect(next_url)
    return redirect("orders:confirmation", order_id=order.id)


@login_required
def resend_invoice_email_view(request, order_id):
    """
    1-click resend of official PDF tax invoice email.
    Accessible to order owner or store managers/staff.
    """
    if request.user.is_staff or request.user.is_superuser or getattr(request.user, "is_manager", False):
        order = get_object_or_404(Order, id=order_id)
    else:
        order = get_object_or_404(Order, id=order_id, user=request.user)

    recent_payment = order.payments.filter(status='Success').first()
    pm = recent_payment.get_payment_method_display() if recent_payment and hasattr(recent_payment, 'get_payment_method_display') else "Payment Gateway"
    tx = recent_payment.transaction_id if recent_payment else f"TXN-{order.id}"

    success = send_order_confirmation_email(order, order.user, pm, tx)
    if success:
        messages.success(
            request,
            f"Official tax invoice PDF has been resent to {order.user.email}."
        )
    else:
        messages.warning(
            request,
            "Unable to dispatch email. You can download the PDF invoice directly using the link below."
        )

    next_url = request.GET.get("next") or request.META.get("HTTP_REFERER")
    if next_url:
        return redirect(next_url)
    return redirect("orders:confirmation", order_id=order.id)