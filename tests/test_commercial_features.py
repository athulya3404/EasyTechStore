from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core import mail
from rest_framework.test import APIClient

from products.models import Product, Category, Brand, Review
from orders.models import Order, OrderItem
from orders.views import (
    send_order_confirmation_email,
    generate_pdf_invoice_response,
    _generate_pure_python_invoice_pdf,
)

User = get_user_model()


class CommercialFeaturesTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="shopper@easytech.com",
            password="StrongPassword123!",
            name="Commercial Shopper",
        )
        self.manager = User.objects.create_user(
            email="manager@easytech.com",
            password="StrongPassword123!",
            name="Store Manager",
            is_staff=True,
        )

        self.category_laptops = Category.objects.create(name="Laptops", slug="laptops", is_active=True)
        self.category_phones = Category.objects.create(name="Smartphones", slug="smartphones", is_active=True)
        self.brand_dell = Brand.objects.create(name="Dell", description="Dell Tech")

        self.product1 = Product.objects.create(
            name="Dell XPS 15",
            slug="dell-xps-15",
            category=self.category_laptops,
            brand=self.brand_dell,
            price=Decimal("150000.00"),
            stock=15,
            is_active=True,
            specifications="RAM: 32GB, Storage: 1TB SSD, Processor: Core i7",
        )
        self.product2 = Product.objects.create(
            name="Dell Latitude 5520",
            slug="dell-latitude-5520",
            category=self.category_laptops,
            brand=self.brand_dell,
            price=Decimal("95000.00"),
            stock=8,
            is_active=True,
            specifications="RAM: 16GB, Storage: 512GB SSD, Processor: Core i5",
        )
        self.product_phone = Product.objects.create(
            name="Pixel 8 Pro",
            slug="pixel-8-pro",
            category=self.category_phones,
            brand=self.brand_dell,
            price=Decimal("79999.00"),
            stock=0,
            is_active=True,
        )

    def test_order_delivery_simulation_and_days_left(self):
        """Test delivery fields auto-assignment, days left calculation, and status progression."""
        order = Order.objects.create(
            user=self.user,
            total_amount=Decimal("150000.00"),
            status=Order.STATUS_PAID,
            shipping_address="77 Silicon Ave, Bengaluru, Karnataka",
            recipient_name="Commercial Shopper",
            recipient_phone="9876543210",
            estimated_delivery_date=timezone.now().date() + timedelta(days=3),
            tracking_number="ETX-TEST1234",
            carrier_name="BlueDart Express",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            price_at_purchase=self.product1.price,
            quantity=1,
        )

        # 1. Check properties
        self.assertEqual(order.delivery_days_left, 3)
        self.assertIn("3 days left", order.delivery_status_display)

        # 2. Advance to Shipped via viva helper view
        self.client.force_login(self.manager)
        resp_shipped = self.client.post(f"/orders/{order.id}/advance-status/")
        self.assertEqual(resp_shipped.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_SHIPPED)
        self.assertIsNotNone(order.shipped_at)
        self.assertIn("days left", order.delivery_status_display)

        # 3. Advance to Delivered
        resp_delivered = self.client.post(f"/orders/{order.id}/advance-status/")
        self.assertEqual(resp_delivered.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_DELIVERED)
        self.assertIsNotNone(order.delivered_at)
        self.assertIn("Delivered on", order.delivery_status_display)

    def test_invoice_email_attachment(self):
        """Test that send_order_confirmation_email attaches a valid PDF invoice."""
        order = Order.objects.create(
            user=self.user,
            total_amount=Decimal("150000.00"),
            status=Order.STATUS_PAID,
            shipping_address="77 Silicon Ave, Bengaluru, Karnataka",
            recipient_name="Commercial Shopper",
            recipient_phone="9876543210",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            price_at_purchase=self.product1.price,
            quantity=1,
        )

        mail.outbox = []
        sent = send_order_confirmation_email(order, self.user, "Sandbox", "TXN-TEST-12345")
        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)

        sent_mail = mail.outbox[0]
        self.assertEqual(sent_mail.to, [self.user.email])
        self.assertEqual(len(sent_mail.attachments), 1)

        filename, content, mimetype = sent_mail.attachments[0]
        self.assertEqual(filename, f"EasyTech_Invoice_#{order.id}.pdf")
        self.assertEqual(mimetype, "application/pdf")
        self.assertTrue(content.startswith(b"%PDF"))

    def test_verified_buyer_review_and_rating_breakdown(self):
        """Test verified buyer review status and 5-star rating breakdown."""
        # Unverified review before purchase
        unverified_review = Review.objects.create(
            user=self.user,
            product=self.product1,
            rating=5,
            comment="Looks great on paper!",
        )
        self.assertFalse(unverified_review.is_verified_purchase)

        # Complete a paid order for product1
        order = Order.objects.create(
            user=self.user,
            total_amount=Decimal("150000.00"),
            status=Order.STATUS_PAID,
            shipping_address="77 Silicon Ave, Bengaluru",
            recipient_name="Commercial Shopper",
            recipient_phone="9876543210",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            price_at_purchase=self.product1.price,
            quantity=1,
        )

        # Re-evaluate review after purchase
        self.assertTrue(unverified_review.is_verified_purchase)

        # Add second review from manager
        Review.objects.create(
            user=self.manager,
            product=self.product1,
            rating=4,
            comment="Solid build quality.",
        )

        breakdown = self.product1.get_rating_breakdown()
        self.assertEqual(breakdown[5]["count"], 1)
        self.assertEqual(breakdown[5]["percent"], 50.0)
        self.assertEqual(breakdown[4]["count"], 1)
        self.assertEqual(breakdown[4]["percent"], 50.0)
        self.assertEqual(breakdown[1]["count"], 0)
        self.assertEqual(breakdown[1]["percent"], 0.0)

    def test_product_comparison_view(self):
        """Test side-by-side comparison view and category validation."""
        # Same category comparison
        resp_valid = self.client.get(f"/products/compare/?p1={self.product1.id}&p2={self.product2.id}")
        self.assertEqual(resp_valid.status_code, 200)
        self.assertContains(resp_valid, "Dell XPS 15")
        self.assertContains(resp_valid, "Dell Latitude 5520")
        self.assertContains(resp_valid, "RAM")

        # Category mismatch comparison
        resp_mismatch = self.client.get(f"/products/compare/?p1={self.product1.id}&p2={self.product_phone.id}")
        self.assertEqual(resp_mismatch.status_code, 200)
        self.assertContains(resp_mismatch, "Comparison is only available between gadgets in the same category")

    def test_manager_analytics_dashboard_data(self):
        """Test manager portal analytics data and Chart.js integration."""
        self.client.force_login(self.manager)
        resp = self.client.get("/manager/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("chart_revenue_labels", resp.context)
        self.assertIn("chart_revenue_data", resp.context)
        self.assertIn("chart_stock_labels", resp.context)
        self.assertIn("chart_stock_data", resp.context)
        self.assertContains(resp, 'id="revenueTrendChart"')
        self.assertContains(resp, 'id="inventoryHealthChart"')

    def test_sales_reports_dss_financial_and_logistics_metrics(self):
        """Test DSS sales reports with GST tax accounting and logistics SLA metrics."""
        # Create a paid order with tax and carrier
        order = Order.objects.create(
            user=self.user,
            subtotal=Decimal("127118.64"),
            tax_amount=Decimal("22881.36"),
            shipping_fee=Decimal("0.00"),
            total_amount=Decimal("150000.00"),
            status=Order.STATUS_PAID,
            carrier_name="BlueDart Express",
            tracking_number="ETX-888999",
            estimated_delivery_date=timezone.now().date() + timedelta(days=3),
            shipping_address="77 Silicon Ave, Bengaluru",
            recipient_name="Commercial Shopper",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            price_at_purchase=self.product1.price,
            quantity=1,
        )

        self.client.force_login(self.manager)
        resp = self.client.get("/manager/dashboard/reports/?range=30days")
        self.assertEqual(resp.status_code, 200)

        # Financial & GST context assertions
        self.assertIn("net_revenue", resp.context)
        self.assertIn("gst_collected", resp.context)
        self.assertIn("gmv", resp.context)
        self.assertGreaterEqual(resp.context["net_revenue"], 127118.64)
        self.assertGreaterEqual(resp.context["gst_collected"], 22881.36)

        # Logistics & tracking context assertions
        self.assertIn("on_time_delivery_rate", resp.context)
        self.assertIn("carrier_performance", resp.context)
        self.assertIn("prepaid_ratio", resp.context)

        # UI element assertions
        self.assertContains(resp, "18% GST Collected")
        self.assertContains(resp, "Net Product Sales")
        self.assertContains(resp, "On-Time Delivery Rate")
        self.assertContains(resp, "Logistics Carrier SLA")
        self.assertContains(resp, "Export to CSV")
        self.assertContains(resp, 'id="dynamicTimelineChart"')
        self.assertContains(resp, 'id="paymentMethodChart"')

    def test_export_sales_report_csv(self):
        """Test itemized CSV spreadsheet export matching active filters."""
        order = Order.objects.create(
            user=self.user,
            subtotal=Decimal("127118.64"),
            tax_amount=Decimal("22881.36"),
            shipping_fee=Decimal("0.00"),
            total_amount=Decimal("150000.00"),
            status=Order.STATUS_PAID,
            carrier_name="BlueDart Express",
            tracking_number="ETX-888999",
            estimated_delivery_date=timezone.now().date() + timedelta(days=3),
            shipping_address="77 Silicon Ave, Bengaluru",
            recipient_name="Commercial Shopper",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            price_at_purchase=self.product1.price,
            quantity=1,
        )

        self.client.force_login(self.manager)
        resp = self.client.get("/manager/dashboard/reports/export-csv/?range=30days")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment; filename=\"EasyTech_Sales_Report_", resp["Content-Disposition"])

        content = resp.content.decode("utf-8")
        self.assertIn("Order ID,Order Date,Customer Name,Customer Email", content)
        self.assertIn(f"#{order.id}", content)
        self.assertIn("127118.64", content)
        self.assertIn("22881.36", content)
        self.assertIn("BlueDart Express", content)
        self.assertIn("ETX-888999", content)

    def test_invoice_sent_at_and_resend_view(self):
        """Test invoice_sent_at timestamp tracking and 1-click resend view for customer & manager."""
        order = Order.objects.create(
            user=self.user,
            total_amount=Decimal("150000.00"),
            status=Order.STATUS_PAID,
            shipping_address="77 Silicon Ave, Bengaluru, Karnataka",
            recipient_name="Commercial Shopper",
            recipient_phone="9876543210",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            price_at_purchase=self.product1.price,
            quantity=1,
        )

        # Initially invoice_sent_at is None
        self.assertIsNone(order.invoice_sent_at)

        # Dispatch email and verify timestamp is updated
        mail.outbox = []
        sent = send_order_confirmation_email(order, self.user, "UPI", "TXN-TEST-12345")
        self.assertTrue(sent)
        order.refresh_from_db()
        self.assertIsNotNone(order.invoice_sent_at)
        initial_sent_time = order.invoice_sent_at

        # Customer triggers 1-click resend invoice view
        self.client.force_login(self.user)
        mail.outbox = []
        resend_resp = self.client.get(f"/orders/{order.id}/resend-invoice/?next=/orders/my-orders/")
        self.assertEqual(resend_resp.status_code, 302)
        self.assertEqual(resend_resp["Location"], "/orders/my-orders/")
        self.assertEqual(len(mail.outbox), 1)

        # Store Manager also has access to resend invoice for this order
        self.client.force_login(self.manager)
        mail.outbox = []
        mgr_resp = self.client.get(f"/orders/{order.id}/resend-invoice/?next=/manager/dashboard/orders/{order.id}/detail/")
        self.assertEqual(mgr_resp.status_code, 302)
        self.assertEqual(mgr_resp["Location"], f"/manager/dashboard/orders/{order.id}/detail/")
        self.assertEqual(len(mail.outbox), 1)

    def test_product_detail_automated_comparison_matrix(self):
        """Test automatic detection of same-category competing products and specification matrix rendering."""
        # Product1 has Product2 in the same category (Laptops)
        resp = self.client.get(f"/products/{self.product1.slug}/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["has_auto_comparison"])
        self.assertEqual(len(resp.context["competing_products"]), 1)
        self.assertEqual(resp.context["competing_products"][0].id, self.product2.id)

        # Check specification attributes in matrix
        matrix_attrs = [row["attribute"] for row in resp.context["auto_comparison_matrix"]]
        self.assertIn("RAM", matrix_attrs)
        self.assertIn("Storage", matrix_attrs)
        self.assertIn("Processor", matrix_attrs)

        # Verify HTML rendered comparison table elements
        self.assertContains(resp, "Compare with Similar Gadgets")
        self.assertContains(resp, "Side-by-Side Comparison")
        self.assertContains(resp, "Current Selection")
        self.assertContains(resp, "Dell Latitude 5520")

        # Category with single item should not render auto comparison
        resp_phone = self.client.get(f"/products/{self.product_phone.slug}/")
        self.assertEqual(resp_phone.status_code, 200)
        self.assertFalse(resp_phone.context["has_auto_comparison"])
        self.assertNotContains(resp_phone, "Compare with Similar Gadgets")

    def test_ask_customer_reviews_after_buying_gadget(self):
        """Test review prompting banner on product detail, my orders, and order confirmation."""
        # 1. Unpurchased product: prompt must NOT appear
        self.client.force_login(self.user)
        resp = self.client.get(f"/products/{self.product1.slug}/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["show_review_prompt"])
        self.assertNotContains(resp, "You Purchased This Gadget!")

        # 2. User purchases product1 (Order Paid)
        order = Order.objects.create(
            user=self.user,
            total_amount=Decimal("150000.00"),
            status=Order.STATUS_PAID,
            invoice_sent_at=timezone.now(),
            shipping_address="77 Silicon Ave, Bengaluru, Karnataka",
            recipient_name="Commercial Shopper",
            recipient_phone="9876543210",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            price_at_purchase=self.product1.price,
            quantity=1,
        )

        # Now product detail should display verified buyer review prompt
        resp_purchased = self.client.get(f"/products/{self.product1.slug}/")
        self.assertEqual(resp_purchased.status_code, 200)
        self.assertTrue(resp_purchased.context["show_review_prompt"])
        self.assertContains(resp_purchased, "You Purchased This Gadget!")
        self.assertContains(resp_purchased, "Write Verified Review")
        self.assertContains(resp_purchased, 'id="write-review"')

        # My Orders page displays 'Write Review' badge button and 'Invoice Emailed' indicator
        resp_orders = self.client.get("/orders/my-orders/")
        self.assertEqual(resp_orders.status_code, 200)
        self.assertContains(resp_orders, "Write Review")
        self.assertContains(resp_orders, "#write-review")
        self.assertContains(resp_orders, "Invoice Emailed")
        self.assertContains(resp_orders, f"/orders/{order.id}/resend-invoice/")

        # Order Confirmation page displays invoice card and review invite
        resp_conf = self.client.get(f"/orders/confirmation/{order.id}/")
        self.assertEqual(resp_conf.status_code, 200)
        self.assertContains(resp_conf, "Official Tax Invoice Emailed")
        self.assertContains(resp_conf, "Tested Your New Gadget? Leave a Verified Review!")
        self.assertContains(resp_conf, "Resend Invoice")

        # Manager order detail page displays PDF Tax Invoice Email card
        self.client.force_login(self.manager)
        resp_mgr_order = self.client.get(f"/manager/dashboard/orders/{order.id}/detail/")
        self.assertEqual(resp_mgr_order.status_code, 200)
        self.assertContains(resp_mgr_order, "PDF Tax Invoice Email")
        self.assertContains(resp_mgr_order, "Resend Tax Invoice Email")

        # 3. User submits review: prompt banner disappears from product detail
        self.client.force_login(self.user)
        Review.objects.create(
            user=self.user,
            product=self.product1,
            rating=5,
            comment="Outstanding performance and battery life!",
        )
        resp_reviewed = self.client.get(f"/products/{self.product1.slug}/")
        self.assertEqual(resp_reviewed.status_code, 200)
        self.assertFalse(resp_reviewed.context["show_review_prompt"])
        self.assertNotContains(resp_reviewed, "You Purchased This Gadget!")

    def test_pdf_invoice_generation_non_blank_stream_and_pure_python(self):
        """Test PDF invoice generator creates compliant, non-empty, non-white text documents."""
        order = Order.objects.create(
            user=self.user,
            total_amount=Decimal("150000.00"),
            subtotal=Decimal("127118.64"),
            tax_amount=Decimal("22881.36"),
            shipping_fee=Decimal("0.00"),
            status=Order.STATUS_PAID,
            shipping_address="77 Silicon Ave, Bengaluru, Karnataka",
            recipient_name="Commercial Shopper",
            recipient_phone="9876543210",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            price_at_purchase=self.product1.price,
            quantity=1,
        )

        # 1. Test generate_pdf_invoice_response view helper
        resp = generate_pdf_invoice_response(order)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("attachment; filename=", resp["Content-Disposition"])
        self.assertGreater(len(resp.content), 500)
        self.assertTrue(resp.content.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF", resp.content)

        # 2. Test pure-Python ISO standard PDF engine
        pure_pdf = _generate_pure_python_invoice_pdf(order)
        self.assertIsInstance(pure_pdf, bytes)
        self.assertGreater(len(pure_pdf), 1000)
        self.assertTrue(pure_pdf.startswith(b"%PDF-1.4\n"))
        self.assertTrue(pure_pdf.endswith(b"%%EOF\n"))

        # Verify dark navy text for product descriptions & totals (no white-on-white text)
        self.assertIn(b"0.06 0.09 0.16 rg", pure_pdf)
        self.assertIn(b"Dell XPS 15", pure_pdf)
        self.assertIn(b"Grand Total Payable:", pure_pdf)

        # Verify exact 20-byte xref table lines
        xref_idx = pure_pdf.find(b"xref\n")
        self.assertNotEqual(xref_idx, -1)
        trailer_idx = pure_pdf.find(b"trailer\n", xref_idx)
        xref_lines = pure_pdf[xref_idx:trailer_idx].decode('ascii').splitlines()
        # Header is "xref" and "0 N"
        for line in xref_lines[2:]:
            if line.strip():
                self.assertEqual(len(line) + 2, 20, f"Xref line '{line}' must be exactly 20 bytes including CRLF")

    def test_order_tracking_amazon_flipkart_format_and_ui(self):
        """Test Amazon/Flipkart order tracking copy: 'Arriving by ... • N days left' and milestone nodes."""
        future_date = timezone.now().date() + timedelta(days=5)
        order = Order.objects.create(
            user=self.user,
            total_amount=Decimal("150000.00"),
            status=Order.STATUS_SHIPPED,
            shipping_address="77 Silicon Ave, Bengaluru, Karnataka",
            recipient_name="Commercial Shopper",
            recipient_phone="9876543210",
            shipped_at=timezone.now(),
            estimated_delivery_date=future_date,
            tracking_number="ETX-AMZ9988",
            carrier_name="BlueDart Express",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            price_at_purchase=self.product1.price,
            quantity=1,
        )

        # 1. Delivery status display property formatting
        status_disp = order.delivery_status_display
        self.assertIn("Arriving by", status_disp)
        self.assertIn("• 5 days left", status_disp)

        # 2. Paid status display formatting
        order.status = Order.STATUS_PAID
        order.save()
        self.assertIn("Preparing for Dispatch • Estimated by", order.delivery_status_display)

        # 3. Delivered status display formatting
        order.status = Order.STATUS_DELIVERED
        order.delivered_at = timezone.now()
        order.save()
        self.assertIn("Delivered on", order.delivery_status_display)
        self.assertIn("Package handed to resident", order.delivery_status_display)

        # 4. My Orders UI tracking validation
        self.client.force_login(self.user)
        resp_orders = self.client.get("/orders/my-orders/")
        self.assertEqual(resp_orders.status_code, 200)
        self.assertContains(resp_orders, "Live Tracking")
        self.assertContains(resp_orders, "BlueDart Express")
        self.assertContains(resp_orders, "#ETX-AMZ9988")
        self.assertContains(resp_orders, "navigator.clipboard.writeText('ETX-AMZ9988')")
        self.assertContains(resp_orders, "Ordered")
        self.assertContains(resp_orders, "Confirmed")
        self.assertContains(resp_orders, "Shipped")
        self.assertContains(resp_orders, "Delivered")

        # 5. Viva demo quick advance button for staff
        self.client.force_login(self.manager)
        resp_mgr_orders = self.client.get("/orders/my-orders/")
        self.assertEqual(resp_mgr_orders.status_code, 200)
        self.assertContains(resp_mgr_orders, "Viva Demo Action")
        self.assertContains(resp_mgr_orders, f"/orders/{order.id}/advance-status/")

    def test_manager_dss_export_sales_report_csv_excel_compatibility(self):
        """Test manager DSS CSV export generates real-time UTF-8 BOM data compatible with Excel."""
        order = Order.objects.create(
            user=self.user,
            total_amount=Decimal("150000.00"),
            subtotal=Decimal("127118.64"),
            tax_amount=Decimal("22881.36"),
            shipping_fee=Decimal("0.00"),
            status=Order.STATUS_PAID,
            shipping_address="77 Silicon Ave, Bengaluru, Karnataka",
            recipient_name="Commercial Shopper",
            recipient_phone="9876543210",
            tracking_number="ETX-CSV123",
            carrier_name="BlueDart Express",
            estimated_delivery_date=timezone.now().date() + timedelta(days=2),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            price_at_purchase=self.product1.price,
            quantity=1,
        )

        self.client.force_login(self.manager)
        resp = self.client.get("/manager/dashboard/reports/export-csv/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment; filename=\"EasyTech_Sales_Report_", resp["Content-Disposition"])

        # Native UTF-8 BOM for Microsoft Excel on Windows
        self.assertTrue(resp.content.startswith(b"\xef\xbb\xbf"))

        # Verify CSV itemized headers and values
        csv_text = resp.content.decode("utf-8-sig")
        self.assertIn("Order ID", csv_text)
        self.assertIn("Integrated GST 18% (INR)", csv_text)
        self.assertIn("Net Subtotal (INR)", csv_text)
        self.assertIn("Logistics Carrier", csv_text)
        self.assertIn("Tracking Number", csv_text)
        self.assertIn(f"#{order.id}", csv_text)
        self.assertIn("127118.64", csv_text)
        self.assertIn("22881.36", csv_text)
        self.assertIn("BlueDart Express", csv_text)
        self.assertIn("ETX-CSV123", csv_text)


