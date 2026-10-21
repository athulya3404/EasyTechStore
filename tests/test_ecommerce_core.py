import json
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db.models import F
from django.utils import timezone
from django.core.management import call_command

from typing import Any
from category.models import Category
from products.models import Product, Brand, Review, Wishlist, ProductImage
from cart.models import Cart, CartItem
from orders.models import Order, OrderItem, Payment
from electronics_shopping_website.users.models import Address

User: Any = get_user_model()


class EcommerceCoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="testcustomer@example.com",
            password="testpassword123",
            name="Test Customer"
        )
        self.category = Category.objects.create(name="Laptops", description="Portable Computers")
        self.brand = Brand.objects.create(name="Dell", description="Dell Technologies")
        self.product = Product.objects.create(
            name="Dell XPS 15",
            price=1000.00,
            discount=10.00,  # 10% off -> 900.00
            stock=15,
            category=self.category,
            brand=self.brand,
            is_active=True,
            specifications="RAM: 16GB\nProcessor: Intel i7"
        )

    def test_discounted_price_calculation(self):
        """Verify discount percentage accurately reduces the price."""
        self.assertEqual(self.product.get_discounted_price(), 900.00)

    def test_review_and_average_rating(self):
        """Verify review creation and dynamic average rating calculation."""
        self.assertEqual(self.product.average_rating, 0.0)
        self.assertEqual(self.product.review_count, 0)

        # Add 5-star review
        Review.objects.create(
            user=self.user,
            product=self.product,
            rating=5,
            comment="Incredible laptop!"
        )
        self.assertEqual(self.product.average_rating, 5.0)
        self.assertEqual(self.product.review_count, 1)

    def test_cart_item_subtotal_with_discount(self):
        """Verify CartItem subtotal uses discounted pricing."""
        cart = Cart.objects.create(user=self.user)
        cart_item = CartItem.objects.create(
            cart=cart,
            product=self.product,
            quantity=2
        )
        # 2 * 900 = 1800
        self.assertEqual(cart_item.get_subtotal(), 1800.00)
        self.assertEqual(cart.get_total_price(), 1800.00)

    def test_customer_address_formatting(self):
        """Verify Address model stores structured address details."""
        address = Address.objects.create(
            user=self.user,
            full_name="John Doe",
            phone_number="9876543210",
            street_address="42 Cyber Valley Road",
            city="Tech City",
            state="California",
            postal_code="94016",
            address_type="Home"
        )
        formatted = address.get_formatted_address()
        self.assertIn("John Doe", formatted)
        self.assertIn("Tech City", formatted)
        self.assertIn("9876543210", formatted)

    def test_atomic_stock_deduction_and_cancel_restore(self):
        """Verify F() stock deduction and cancellation restoration."""
        initial_stock = self.product.stock  # 15
        qty_to_buy = 3

        # Simulate Order placement
        order = Order.objects.create(
            user=self.user,
            shipping_address="42 Cyber Valley Road",
            status="Paid",
            total_amount=2700.00
        )
        order_item = OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=qty_to_buy,
            price_at_purchase=900.00
        )

        # Deduct stock
        Product.objects.filter(id=self.product.id).update(stock=F('stock') - qty_to_buy)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 12)

        # Simulate Order cancellation
        Product.objects.filter(id=self.product.id).update(stock=F('stock') + qty_to_buy)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 15)

    def test_cart_remove_item_api(self):
        """Verify /api/cart/remove_item/<id>/ removes the cart item successfully."""
        cart = Cart.objects.create(user=self.user)
        cart_item = CartItem.objects.create(cart=cart, product=self.product, quantity=1)

        client = Client()
        client.force_login(self.user)
        
        # Test DELETE method
        response_delete = client.delete(f"/api/cart/remove_item/{cart_item.id}/")
        self.assertEqual(response_delete.status_code, 200)
        self.assertFalse(CartItem.objects.filter(id=cart_item.id).exists())

        # Test POST method with a new cart item
        cart_item2 = CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        response_post = client.post(f"/api/cart/remove_item/{cart_item2.id}/")
        self.assertEqual(response_post.status_code, 200)
        self.assertFalse(CartItem.objects.filter(id=cart_item2.id).exists())

    def test_cart_update_quantity_api(self):
        """Verify /api/cart/update_quantity/<id>/ updates the cart item quantity."""
        cart = Cart.objects.create(user=self.user)
        cart_item = CartItem.objects.create(cart=cart, product=self.product, quantity=1)

        client = Client()
        client.force_login(self.user)

        response = client.post(
            f"/api/cart/update_quantity/{cart_item.id}/",
            data='{"quantity": 3}',
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        cart_item.refresh_from_db()
        self.assertEqual(cart_item.quantity, 3)

    def test_selective_cart_item_checkout(self):
        """Verify checking out only 1 of 2 cart items leaves the unselected item in cart."""
        cart = Cart.objects.create(user=self.user)
        product_b = Product.objects.create(
            name="Mechanical Keyboard",
            price=200.00,
            stock=10,
            category=self.category,
            brand=self.brand,
            is_active=True
        )

        item_a = CartItem.objects.create(cart=cart, product=self.product, quantity=1)  # 900
        item_b = CartItem.objects.create(cart=cart, product=product_b, quantity=2)      # 400

        client = Client()
        client.force_login(self.user)

        # Checkout ONLY item_a
        payload = {
            "shipping_address": "123 Tech Boulevard",
            "payment_method": "Sandbox",
            "selected_item_ids": [item_a.id]
        }
        response = client.post(
            "/api/orders/place_order/",
            data=payload,
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        
        # Verify created order has only 1 item and amount is 900
        order = Order.objects.get(id=data["order_id"])
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(float(order.total_amount), 900.00)
        first_order_item = order.items.first()
        self.assertIsNotNone(first_order_item)
        assert first_order_item is not None
        self.assertEqual(first_order_item.product.id, self.product.id)

        # Verify item_a is removed from cart, but item_b is STILL in the cart!
        self.assertFalse(CartItem.objects.filter(id=item_a.id).exists())
        self.assertTrue(CartItem.objects.filter(id=item_b.id).exists())
        self.assertEqual(cart.items.count(), 1)
        first_cart_item = cart.items.first()
        self.assertIsNotNone(first_cart_item)
        assert first_cart_item is not None
        self.assertEqual(first_cart_item.product.id, product_b.id)

    def test_category_sample_template_download(self):
        """Verify manager can download sample category Excel template."""
        staff_user = User.objects.create_user(
            email="manager@example.com",
            password="testpassword123",
            is_staff=True
        )
        client = Client()
        client.force_login(staff_user)

        response = client.get("/manager/dashboard/categories/sample-template/")
        self.assertEqual(response.status_code, 200)

        # Test explicit CSV format download
        response_csv = client.get("/manager/dashboard/categories/sample-template/?format=csv")
        self.assertEqual(response_csv.status_code, 200)
        self.assertIn("text/csv", response_csv["Content-Type"])
        self.assertIn("easytech_categories_template.csv", response_csv["Content-Disposition"])
        self.assertIn("Category Name,Description,Active", response_csv.content.decode("utf-8"))

    def test_category_bulk_import_csv(self):
        """Verify bulk category import from CSV file and ensure existing categories are NOT overwritten."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        staff_user = User.objects.create_user(
            email="admin_import@example.com",
            password="testpassword123",
            is_staff=True
        )
        client = Client()
        client.force_login(staff_user)

        # Note: self.category has name="Laptops", description="Portable Computers", is_active=True
        csv_content = (
            "Category Name,Description,Active\n"
            "Laptops,Attempted Overwrite Of Description,No\n"
            "Gaming Laptops,High performance GPUs,Yes\n"
            "Smart Glasses,Augmented reality wearables,Yes\n"
            "Drones & Quadcopters,4K camera aerial drones,No\n"
        ).encode("utf-8")

        uploaded_csv = SimpleUploadedFile("categories.csv", csv_content, content_type="text/csv")

        response = client.post(
            "/manager/dashboard/categories/import/",
            {"excel_file": uploaded_csv},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        
        # 1. Verify existing 'Laptops' category was NOT overwritten
        self.category.refresh_from_db()
        self.assertEqual(self.category.description, "Portable Computers")
        self.assertTrue(self.category.is_active)

        # 2. Verify newly imported categories exist in DB
        self.assertTrue(Category.objects.filter(name="Gaming Laptops", is_active=True).exists())
        self.assertTrue(Category.objects.filter(name="Smart Glasses", is_active=True).exists())
        self.assertTrue(Category.objects.filter(name="Drones & Quadcopters", is_active=False).exists())

    def test_manager_category_pages_render_without_reverse_error(self):
        """Verify manager category dashboard, add, and import pages render without NoReverseMatch."""
        from django.urls import reverse

        staff_user = User.objects.create_user(
            email="manager_pages@example.com",
            password="testpassword123",
            is_staff=True
        )
        client = Client()
        client.force_login(staff_user)

        # Test URL reverses
        self.assertEqual(reverse("manager:category_import"), "/manager/dashboard/categories/import/")
        self.assertEqual(reverse("manager:category_sample_template"), "/manager/dashboard/categories/sample-template/")
        self.assertEqual(reverse("category_import"), "/categories/import/")
        self.assertEqual(reverse("category_sample_template"), "/categories/sample-template/")

        # Test view render
        res_categories = client.get("/manager/dashboard/categories/")
        self.assertEqual(res_categories.status_code, 200)

        res_add = client.get("/manager/dashboard/categories/add/")
        self.assertEqual(res_add.status_code, 200)

        res_import = client.get("/manager/dashboard/categories/import/")
        self.assertEqual(res_import.status_code, 200)

    def test_brand_bulk_import_with_categories_and_no_overwrite(self):
        """Verify bulk brand import maps categories (e.g. HP under Laptops) and preserves existing brands."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        staff_user = User.objects.create_user(
            email="brand_admin@example.com",
            password="testpassword123",
            is_staff=True
        )
        client = Client()
        client.force_login(staff_user)

        # Note: self.brand has name="Dell", description="Dell Technologies"
        csv_content = (
            "Brand Name,Category,Description\n"
            "Dell,Laptops,Attempted Description Overwrite\n"
            "HP,Laptops,Hewlett-Packard laptops and computers\n"
            "Apple,\"Laptops, Smartphones\",Apple premium devices\n"
            "Sony,Audio & Headphones,Sony audio and PlayStation\n"
        ).encode("utf-8")

        uploaded_csv = SimpleUploadedFile("brands.csv", csv_content, content_type="text/csv")

        response = client.post(
            "/manager/dashboard/brands/import/",
            {"excel_file": uploaded_csv},
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        # 1. Verify existing brand 'Dell' was NOT overwritten
        self.brand.refresh_from_db()
        self.assertEqual(self.brand.description, "Dell Technologies")
        # Dell should have 'Laptops' category linked
        self.assertTrue(self.brand.categories.filter(name="Laptops").exists())

        # 2. Verify 'HP' was created and linked under 'Laptops'
        hp = Brand.objects.get(name="HP")
        self.assertEqual(hp.description, "Hewlett-Packard laptops and computers")
        self.assertTrue(hp.categories.filter(name="Laptops").exists())

        # 3. Verify 'Apple' was linked under both 'Laptops' and auto-created 'Smartphones'
        apple = Brand.objects.get(name="Apple")
        self.assertTrue(apple.categories.filter(name="Laptops").exists())
        self.assertTrue(apple.categories.filter(name="Smartphones").exists())

        # 4. Verify 'Sony' created with auto-created 'Audio & Headphones' category
        sony = Brand.objects.get(name="Sony")
        self.assertTrue(sony.categories.filter(name="Audio & Headphones").exists())

    def test_manager_brand_pages_and_template_downloads(self):
        """Verify brand dashboard, import, sample template download, and add/edit render cleanly."""
        from django.urls import reverse

        staff_user = User.objects.create_user(
            email="brand_tester@example.com",
            password="testpassword123",
            is_staff=True
        )
        client = Client()
        client.force_login(staff_user)

        # URL reverse checks
        self.assertEqual(reverse("manager:brand_import"), "/manager/dashboard/brands/import/")
        self.assertEqual(reverse("manager:brand_sample_template"), "/manager/dashboard/brands/sample-template/")
        self.assertEqual(reverse("brand_import"), "/brands/import/")
        self.assertEqual(reverse("brand_sample_template"), "/brands/sample-template/")

        # View rendering checks
        res_brands = client.get("/manager/dashboard/brands/")
        self.assertEqual(res_brands.status_code, 200)

        res_add = client.get("/manager/dashboard/brands/add/")
        self.assertEqual(res_add.status_code, 200)

        res_edit = client.get(f"/manager/dashboard/brands/{self.brand.id}/edit/")
        self.assertEqual(res_edit.status_code, 200)

        res_import = client.get("/manager/dashboard/brands/import/")
        self.assertEqual(res_import.status_code, 200)

        # Template download (Excel and CSV)
        res_tmpl = client.get("/manager/dashboard/brands/sample-template/")
        self.assertEqual(res_tmpl.status_code, 200)

        res_tmpl_csv = client.get("/manager/dashboard/brands/sample-template/?format=csv")
        self.assertEqual(res_tmpl_csv.status_code, 200)
        self.assertIn("text/csv", res_tmpl_csv["Content-Type"])
        self.assertIn("Brand Name,Category,Description", res_tmpl_csv.content.decode("utf-8"))

    def test_product_bulk_import_with_category_and_brand_no_overwrite(self):
        """Verify bulk product import links category and brand, parses pricing/specs, and protects existing products."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        staff_user = User.objects.create_user(
            email="product_admin@example.com",
            password="testpassword123",
            is_staff=True
        )
        client = Client()
        client.force_login(staff_user)

        # Note: self.product has name="Dell XPS 15", price=1000.00, stock=15
        csv_content = (
            "Product Name,Category,Brand,Price,Discount (%),Stock,Photo URL,Specifications,Description,Active\n"
            "Dell XPS 15,Laptops,Dell,2999.99,50,99,https://example.com/dell.jpg,Attempted Overwrite,Attempted Overwrite Desc,No\n"
            "HP Pavilion 15,Laptops,HP,850.00,10,20,products/hp_pavilion.jpg,\"RAM: 16GB, CPU: i7\",Multitasking laptop,Yes\n"
            "Samsung Galaxy S24,Smartphones,Samsung,1199.99,5,30,https://example.com/s24.jpg,\"Display: 6.2 AMOLED\",Flagship Galaxy,Yes\n"
        ).encode("utf-8")

        uploaded_csv = SimpleUploadedFile("products.csv", csv_content, content_type="text/csv")

        response = client.post(
            "/manager/dashboard/products/import/",
            {"excel_file": uploaded_csv},
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        # 1. Verify existing product 'Dell XPS 15' was NOT overwritten
        self.product.refresh_from_db()
        self.assertEqual(float(self.product.price), 1000.00)
        self.assertEqual(self.product.stock, 15)
        self.assertTrue(self.product.is_active)

        # 2. Verify new product 'HP Pavilion 15' was created with brand 'HP' and category 'Laptops'
        hp_prod = Product.objects.get(name="HP Pavilion 15")
        self.assertEqual(float(hp_prod.price), 850.00)
        self.assertEqual(float(hp_prod.discount), 10.00)
        self.assertEqual(hp_prod.stock, 20)
        self.assertIsNotNone(hp_prod.category)
        self.assertIsNotNone(hp_prod.brand)
        assert hp_prod.category is not None and hp_prod.brand is not None
        self.assertEqual(hp_prod.category.name, "Laptops")
        self.assertEqual(hp_prod.brand.name, "HP")
        self.assertIn("RAM", hp_prod.specifications)
        self.assertTrue(hp_prod.is_active)
        self.assertEqual(str(hp_prod.image), "products/hp_pavilion.jpg")

        # Verify brand 'HP' is now also linked under category 'Laptops'
        self.assertTrue(hp_prod.brand.categories.filter(name="Laptops").exists())

        # 3. Verify 'Samsung Galaxy S24' created with auto-created category 'Smartphones' and brand 'Samsung'
        samsung_prod = Product.objects.get(name="Samsung Galaxy S24")
        self.assertEqual(float(samsung_prod.price), 1199.99)
        self.assertIsNotNone(samsung_prod.category)
        self.assertIsNotNone(samsung_prod.brand)
        assert samsung_prod.category is not None and samsung_prod.brand is not None
        self.assertEqual(samsung_prod.category.name, "Smartphones")
        self.assertEqual(samsung_prod.brand.name, "Samsung")
        self.assertTrue(samsung_prod.brand.categories.filter(name="Smartphones").exists())

    def test_manager_product_import_pages_and_template_downloads(self):
        """Verify product import page, reverse routes, and sample templates render cleanly."""
        from django.urls import reverse

        staff_user = User.objects.create_user(
            email="product_tester@example.com",
            password="testpassword123",
            is_staff=True
        )
        client = Client()
        client.force_login(staff_user)

        # URL reverse checks
        self.assertEqual(reverse("manager:product_import"), "/manager/dashboard/products/import/")
        self.assertEqual(reverse("manager:product_sample_template"), "/manager/dashboard/products/sample-template/")
        self.assertEqual(reverse("product_import"), "/products/import/")
        self.assertEqual(reverse("product_sample_template"), "/products/sample-template/")

        # View rendering checks
        res_import = client.get("/manager/dashboard/products/import/")
        self.assertEqual(res_import.status_code, 200)

        # Template download (Excel and CSV)
        res_tmpl = client.get("/manager/dashboard/products/sample-template/")
        self.assertEqual(res_tmpl.status_code, 200)

        res_tmpl_csv = client.get("/manager/dashboard/products/sample-template/?format=csv")
        self.assertEqual(res_tmpl_csv.status_code, 200)
        self.assertIn("text/csv", res_tmpl_csv["Content-Type"])
        self.assertIn("Product Name,Category,Brand,Price", res_tmpl_csv.content.decode("utf-8"))
        self.assertIn("Photo URL", res_tmpl_csv.content.decode("utf-8"))

    def test_product_import_ajax_percentage_response(self):
        """Verify AJAX product import returns JSON with redirect_url and success status for progress percentage."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        staff_user = User.objects.create_user(
            email="ajax_import@example.com",
            password="testpassword123",
            is_staff=True
        )
        client = Client()
        client.force_login(staff_user)

        csv_content = (
            "Product Name,Category,Brand,Price,Discount (%),Stock,Photo URL,Specifications,Description,Active\n"
            "Asus ROG Zephyrus,Laptops,Asus,1799.00,0,10,https://example.com/rog.jpg,Ryzen 9,Gaming powerhouse,Yes\n"
        ).encode("utf-8")

        uploaded_csv = SimpleUploadedFile("rog.csv", csv_content, content_type="text/csv")

        response = client.post(
            "/manager/dashboard/products/import/",
            {"excel_file": uploaded_csv},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data.get("success"))
        self.assertEqual(json_data.get("created_count"), 1)
        self.assertEqual(json_data.get("redirect_url"), "/manager/dashboard/products/")
        self.assertTrue(Product.objects.filter(name="Asus ROG Zephyrus").exists())

    def test_product_import_sequential_parse_and_item_endpoints(self):
        """Verify sequential parsing and item-by-item upload endpoints for live progress and time left."""
        import json
        from django.core.files.uploadedfile import SimpleUploadedFile

        staff_user = User.objects.create_user(
            email="seq_import@example.com",
            password="testpassword123",
            is_staff=True
        )
        client = Client()
        client.force_login(staff_user)

        # 1. Test Parse Endpoint
        csv_content = (
            "Product Name,Category,Brand,Price,Discount (%),Stock,Photo URL,Specifications,Description,Active\n"
            "Razer Blade 16,Gaming Laptops,Razer,2699.99,5,8,https://example.com/blade.jpg,Intel i9,Ultra fast,Yes\n"
            "Keychron Q1 Pro,Keyboards,Keychron,199.00,0,25,,Wireless Custom,Mechanical,Yes\n"
        ).encode("utf-8")

        uploaded_file = SimpleUploadedFile("batch.csv", csv_content, content_type="text/csv")

        parse_res = client.post(
            "/manager/dashboard/products/import/parse/",
            {"excel_file": uploaded_file},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(parse_res.status_code, 200)
        parse_json = parse_res.json()
        self.assertTrue(parse_json.get("success"))
        self.assertEqual(parse_json.get("total_items"), 2)
        items = parse_json.get("items")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["name"], "Razer Blade 16")
        self.assertEqual(items[1]["name"], "Keychron Q1 Pro")

        # 2. Test Item Import Endpoint (First item)
        item1_res = client.post(
            "/manager/dashboard/products/import/item/",
            data=json.dumps(items[0]),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(item1_res.status_code, 200)
        item1_json = item1_res.json()
        self.assertTrue(item1_json.get("success"))
        self.assertEqual(item1_json["result"]["status"], "created")
        self.assertEqual(item1_json["result"]["name"], "Razer Blade 16")

        prod1 = Product.objects.get(name="Razer Blade 16")
        self.assertIsNotNone(prod1.category)
        self.assertIsNotNone(prod1.brand)
        assert prod1.category is not None and prod1.brand is not None
        self.assertEqual(prod1.category.name, "Gaming Laptops")
        self.assertEqual(prod1.brand.name, "Razer")
        self.assertTrue(prod1.brand.categories.filter(name="Gaming Laptops").exists())

        # 3. Test Item Import Endpoint with existing product (No overwrite)
        item1_duplicate_res = client.post(
            "/manager/dashboard/products/import/item/",
            data=json.dumps(items[0]),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(item1_duplicate_res.status_code, 200)
        dup_json = item1_duplicate_res.json()
        self.assertTrue(dup_json.get("success"))
        self.assertEqual(dup_json["result"]["status"], "already_exists")
        # Ensure count did not increase
        self.assertEqual(Product.objects.filter(name="Razer Blade 16").count(), 1)

        # 4. Test Item Import Endpoint (Second item)
        item2_res = client.post(
            "/manager/dashboard/products/import/item/",
            data=json.dumps(items[1]),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(item2_res.status_code, 200)
        item2_json = item2_res.json()
        self.assertTrue(item2_json.get("success"))
        self.assertEqual(item2_json["result"]["status"], "created")
        self.assertEqual(item2_json["result"]["name"], "Keychron Q1 Pro")
        self.assertTrue(Product.objects.filter(name="Keychron Q1 Pro").exists())

    def test_product_bulk_delete_and_selection(self):
        """Verify bulk deletion of selected products via standard POST and AJAX."""
        staff_user = User.objects.create_user(
            email="bulk_delete_mgr@example.com",
            password="testpassword123",
            is_staff=True
        )
        client = Client()
        client.force_login(staff_user)

        cat = Category.objects.create(name="Audio Devices")
        p1 = Product.objects.create(name="Headphones Alpha", category=cat, price=99.00)
        p2 = Product.objects.create(name="Earbuds Beta", category=cat, price=49.00)
        p3 = Product.objects.create(name="Speaker Gamma", category=cat, price=149.00)

        self.assertEqual(reverse("manager:product_bulk_delete"), "/manager/dashboard/products/bulk-delete/")
        self.assertEqual(reverse("product_bulk_delete"), "/products/bulk-delete/")

        # Bulk delete p1 and p2
        response = client.post(
            "/manager/dashboard/products/bulk-delete/",
            {"product_ids": [p1.id, p2.id]},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(id=p1.id).exists())
        self.assertFalse(Product.objects.filter(id=p2.id).exists())
        self.assertTrue(Product.objects.filter(id=p3.id).exists())

        # Test AJAX bulk delete for p3
        ajax_resp = client.post(
            "/manager/dashboard/products/bulk-delete/",
            json.dumps({"product_ids": [p3.id]}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(ajax_resp.status_code, 200)
        ajax_data = ajax_resp.json()
        self.assertTrue(ajax_data.get("success"))
        self.assertEqual(ajax_data.get("deleted_count"), 1)
        self.assertFalse(Product.objects.filter(id=p3.id).exists())

    def test_slug_generation_and_product_lookup(self):
        """Verify Category and Product auto-slug generation and SEO slug routing."""
        cat = Category.objects.create(name="Smart Watches & Wearables")
        self.assertEqual(cat.slug, "smart-watches-wearables")

        prod = Product.objects.create(
            name="Apple Watch Ultra 2",
            category=cat,
            price=799.00,
            stock=10
        )
        self.assertEqual(prod.slug, "apple-watch-ultra-2")

        client = Client()
        # Lookup via slug
        res = client.get(f"/products/{prod.slug}/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Apple Watch Ultra 2")

    def test_user_profile_idor_protection(self):
        """Verify customer cannot access other customers' profiles (IDOR vulnerability prevention)."""
        other_user = User.objects.create_user(
            email="otheruser@example.com",
            password="password123",
            name="Other User"
        )
        client = Client()
        client.force_login(self.user)

        # Access own profile -> 200
        own_res = client.get(f"/users/{self.user.pk}/")
        self.assertEqual(own_res.status_code, 200)

        # Access other user's profile -> 403 Forbidden
        other_res = client.get(f"/users/{other_user.pk}/")
        self.assertEqual(other_res.status_code, 403)

        # Staff user can access any profile -> 200
        staff_user = User.objects.create_user(
            email="staff@example.com",
            password="password123",
            is_staff=True
        )
        staff_client = Client()
        staff_client.force_login(staff_user)
        staff_res = staff_client.get(f"/users/{other_user.pk}/")
        self.assertEqual(staff_res.status_code, 200)

    def test_two_stage_sandbox_payment_and_verification(self):
        """Verify two-stage checkout: Pending order creation -> Sandbox Gateway -> Backend Verification."""
        cart = Cart.objects.create(user=self.user)
        cart_item = CartItem.objects.create(cart=cart, product=self.product, quantity=2)

        client = Client()
        client.force_login(self.user)

        # Stage 1: Place Order
        order_payload = {
            "shipping_address": "123 Tech Boulevard",
            "payment_method": "Card",
            "selected_item_ids": [cart_item.id]
        }
        res = client.post(
            "/api/orders/place_order/",
            data=json.dumps(order_payload),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertTrue(data.get("success"))
        order_id = data["order_id"]
        order = Order.objects.get(id=order_id)
        self.assertEqual(order.status, "Pending")
        self.assertIn(f"/orders/payment-gateway/{order_id}/", data["redirect_url"])

        # Check payment gateway page renders
        gw_res = client.get(f"/orders/payment-gateway/{order_id}/")
        self.assertEqual(gw_res.status_code, 200)
        self.assertContains(gw_res, "EasyTech Secure Gateway")

        # Stage 2: Verification Simulation (Fail -> transitions to Cancelled and restores stock)
        verify_fail = client.post(
            "/api/payments/verify/",
            data=json.dumps({
                "order_id": order_id,
                "payment_method": "Card",
                "simulated_action": "fail"
            }),
            content_type="application/json"
        )
        self.assertEqual(verify_fail.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, "Payment_Pending")
        self.assertEqual(order.payment.status, "Failed")

        # Stage 2: Verification Simulation (Success on fresh order)
        cart2, _ = Cart.objects.get_or_create(user=self.user)
        cart_item2 = CartItem.objects.create(cart=cart2, product=self.product, quantity=2)
        self.product.refresh_from_db()
        initial_stock = self.product.stock

        res2 = client.post(
            "/api/orders/place_order/",
            data=json.dumps({
                "shipping_address": "456 Gateway Road",
                "payment_method": "Card",
                "selected_item_ids": [cart_item2.id]
            }),
            content_type="application/json"
        )
        self.assertEqual(res2.status_code, 201)
        order2_id = res2.json()["order_id"]
        order2 = Order.objects.get(id=order2_id)

        verify_success = client.post(
            "/api/payments/verify/",
            data=json.dumps({
                "order_id": order2_id,
                "payment_method": "Card (Visa)",
                "simulated_action": "success"
            }),
            content_type="application/json"
        )
        self.assertEqual(verify_success.status_code, 200)
        verify_data = verify_success.json()
        self.assertTrue(verify_data.get("success"))
        order2.refresh_from_db()
        self.assertEqual(order2.status, "Paid")
        self.assertEqual(order2.payment.payment_status, "Success")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial_stock - 2)

    def test_product_and_order_serializers(self):
        """Verify DRF ProductSerializer and OrderSerializer have all required fields."""
        from products.serializers import ProductSerializer
        from orders.serializers import OrderSerializer

        prod_serializer = ProductSerializer(self.product)
        prod_data = prod_serializer.data
        self.assertIn("brand", prod_data)
        self.assertIn("brand_name", prod_data)
        self.assertIn("discount", prod_data)
        self.assertIn("discounted_price", prod_data)
        self.assertIn("specifications", prod_data)
        self.assertIn("stock_status", prod_data)
        self.assertIn("average_rating", prod_data)
        self.assertIn("review_count", prod_data)
        self.assertIn("slug", prod_data)
        self.assertEqual(float(prod_data["discounted_price"]), 900.0)
        self.assertEqual(prod_data["stock_status"], "In Stock")

        order = Order.objects.create(
            user=self.user,
            shipping_address="77 Silicon Ave",
            total_amount=900.00,
            status="Paid"
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            price_at_purchase=900.00
        )
        order_serializer = OrderSerializer(order)
        order_data = order_serializer.data
        self.assertEqual(order_data["id"], order.id)
        self.assertEqual(order_data["status"], "Paid")
        self.assertEqual(len(order_data["items"]), 1)
        self.assertEqual(order_data["items"][0]["product_name"], "Dell XPS 15")

    def test_manager_user_management_and_status_toggle(self):
        """Verify manager Customer Directory view and customer status toggle endpoint."""
        staff = User.objects.create_user(
            email="usermanager@example.com",
            password="password123",
            is_staff=True
        )
        client = Client()
        client.force_login(staff)

        # Customer directory view
        res = client.get("/manager/dashboard/users/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Customer Directory")
        self.assertContains(res, self.user.email)

        # View customer detail
        detail_res = client.get(f"/manager/dashboard/users/{self.user.id}/")
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, self.user.email)

        # Toggle status (active -> inactive)
        toggle_res = client.post(
            f"/manager/dashboard/users/{self.user.id}/toggle-status/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(toggle_res.status_code, 200)
        t_data = toggle_res.json()
        self.assertTrue(t_data.get("success"))
        self.assertFalse(t_data.get("is_active"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_customer_address_book_management(self):
        """Verify customer address creation, listing, and deletion."""
        client = Client()
        client.force_login(self.user)

        # Add new address via POST
        add_res = client.post(
            "/users/addresses/add/",
            {
                "full_name": "Test Recipient",
                "phone_number": "9123456780",
                "street_address": "100 MG Road",
                "city": "Bengaluru",
                "state": "Karnataka",
                "postal_code": "560001",
                "address_type": "Home",
                "is_default": "on"
            },
            follow=True
        )
        self.assertEqual(add_res.status_code, 200)
        new_addr = Address.objects.filter(user=self.user, street_address="100 MG Road").first()
        self.assertIsNotNone(new_addr)
        self.assertTrue(new_addr.is_default)

        # Delete address
        del_res = client.post(f"/users/addresses/{new_addr.id}/delete/", follow=True)
        self.assertEqual(del_res.status_code, 200)
        self.assertFalse(Address.objects.filter(id=new_addr.id).exists())

    def test_product_detail_url_reversing_and_view(self):
        """Verify product_detail reverses by slug or PK, get_absolute_url works, and related products render."""
        # 1. Reverse with slug positional and kwarg
        self.assertEqual(reverse("product_detail", args=["corsair-m1"]), "/products/corsair-m1/")
        self.assertEqual(reverse("product_detail", kwargs={"slug": "corsair-m1"}), "/products/corsair-m1/")

        # 2. Reverse with pk positional and kwarg
        self.assertEqual(reverse("product_detail", args=[self.product.pk]), f"/products/{self.product.pk}/")
        self.assertEqual(reverse("product_detail", kwargs={"pk": self.product.pk}), f"/products/{self.product.pk}/")

        # 3. Test get_absolute_url
        self.assertEqual(self.product.get_absolute_url(), f"/products/{self.product.slug}/")

        # 4. Create related product in same category with slug
        related = Product.objects.create(
            name="Corsair M1",
            slug="corsair-m1",
            price=50.00,
            stock=10,
            category=self.category,
            brand=self.brand,
            is_active=True,
        )

        # 5. Render product detail page (which renders related products with {% url 'product_detail' rel.slug|default:rel.id %})
        client = Client()
        response = client.get(self.product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, related.name)
        self.assertContains(response, "/products/corsair-m1/")

    # Aliases matching external review & walkthrough test names
    test_two_stage_sandbox_payment_flow = test_two_stage_sandbox_payment_and_verification
    test_idor_protection = test_user_profile_idor_protection

    def test_payment_gateway_url_remapping_and_reverse(self):
        """Verify namespaced payment gateway and checkout URLs reverse and resolve correctly."""
        self.assertEqual(reverse("orders:payment_gateway", args=[42]), "/orders/payment-gateway/42/")
        self.assertEqual(reverse("orders:payment", args=[42]), "/orders/payment/42/")
        self.assertEqual(reverse("orders:process_payment", args=[42]), "/orders/process-payment/42/")
        self.assertEqual(reverse("orders:checkout"), "/orders/checkout/")
        self.assertEqual(reverse("orders:confirmation", args=[42]), "/orders/confirmation/42/")
        self.assertEqual(reverse("orders:my_orders"), "/orders/my-orders/")
        self.assertEqual(reverse("orders:cancel_order", args=[42]), "/orders/42/cancel/")
        self.assertEqual(reverse("api_verify_payment"), "/api/payments/verify/")
        self.assertEqual(reverse("api_orders_verify_payment"), "/api/orders/verify_payment/")

    def test_checkout_form_post_and_sandbox_gateway_redirect(self):
        """Verify standard HTML form POST to checkout routes to Payment Gateway."""
        cart = Cart.objects.create(user=self.user)
        cart_item = CartItem.objects.create(cart=cart, product=self.product, quantity=1)

        client = Client()
        client.force_login(self.user)

        # 1. GET Checkout page: contains Payment Gateway (UPI, Card, etc.) and NO 256-Bit/Simulated/Sandbox
        get_res = client.get("/orders/checkout/")
        self.assertEqual(get_res.status_code, 200)
        self.assertContains(get_res, "Payment Gateway")
        self.assertContains(get_res, "(UPI, Card, etc.)")
        self.assertNotContains(get_res, "Sandbox Gateway Simulator")
        self.assertNotContains(get_res, "256-Bit")
        self.assertNotContains(get_res, "Simulated")

        # 2. Standard HTML form POST
        post_res = client.post(
            "/orders/checkout/",
            {
                "shipping_address": "99 Silicon Hill, Bangalore",
                "paymentMethod": "Sandbox",
                "selected_item_ids": f"{cart_item.id}",
            }
        )
        self.assertEqual(post_res.status_code, 302)
        created_order = Order.objects.filter(user=self.user, shipping_address="99 Silicon Hill, Bangalore").first()
        self.assertIsNotNone(created_order)
        assert created_order is not None
        self.assertEqual(created_order.status, "Pending")
        self.assertIsNotNone(created_order.expires_at)
        redirect_url = getattr(post_res, "url", "")
        self.assertIn(f"/orders/payment-gateway/{created_order.id}/", redirect_url)

        # 3. Access Payment Gateway page: clean header with NO 256-Bit/Simulated/Sandbox
        gw_page = client.get(redirect_url)
        self.assertEqual(gw_page.status_code, 200)
        self.assertContains(gw_page, "Payment Gateway")
        self.assertContains(gw_page, "(UPI, Card, etc.)")
        self.assertContains(gw_page, "EasyTech Secure Gateway")
        self.assertContains(gw_page, "Secure Payment")
        self.assertNotContains(gw_page, "Sandbox Gateway Simulator")
        self.assertNotContains(gw_page, "256-Bit")
        self.assertNotContains(gw_page, "Simulated")

    def test_payments_module_helpers(self):
        """Verify orders.payments module token, signature, and handshake helper functions."""
        from orders.payments import (
            generate_transaction_reference,
            generate_payment_signature,
            verify_payment_signature,
            simulate_gateway_handshake,
        )

        txn = generate_transaction_reference()
        self.assertTrue(txn.startswith("TXN-"))
        self.assertGreater(len(txn), 8)

        sig = generate_payment_signature(101, "999.00")
        self.assertTrue(isinstance(sig, str))
        self.assertTrue(verify_payment_signature(101, "999.00", sig))
        self.assertFalse(verify_payment_signature(101, "1000.00", sig))

        valid_upi, err = simulate_gateway_handshake("UPI", upi_vpa="user@oksbi")
        self.assertTrue(valid_upi)
        self.assertIsNone(err)

        invalid_upi, err = simulate_gateway_handshake("UPI", upi_vpa="invalid_vpa")
        self.assertFalse(invalid_upi)
        self.assertIsNotNone(err)

    def test_order_expiration_and_cleanup_command(self):
        """Verify cleanup_expired_orders cancels orders past 15 minutes and restores stock."""
        initial_stock = self.product.stock  # 15
        qty = 3

        # Create an expired pending order
        expired_order = Order.objects.create(
            user=self.user,
            shipping_address="12 Expired St",
            status=Order.STATUS_PENDING,
            total_amount=2700.00,
            expires_at=timezone.now() - timedelta(minutes=5)
        )
        OrderItem.objects.create(
            order=expired_order,
            product=self.product,
            quantity=qty,
            price_at_purchase=900.00
        )
        Product.objects.filter(id=self.product.id).update(stock=F('stock') - qty)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial_stock - qty)

        # Run the cleanup command
        call_command("cleanup_expired_orders")

        # Order must now be Cancelled and stock restored
        expired_order.refresh_from_db()
        self.assertEqual(expired_order.status, Order.STATUS_CANCELLED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial_stock)

    def test_payment_retry_flow_and_fk_relationship(self):
        """Verify failed payment logs Payment attempt without killing order, allowing retry."""
        order = Order.objects.create(
            user=self.user,
            shipping_address="42 Retry Way",
            status=Order.STATUS_PENDING,
            total_amount=900.00,
            expires_at=timezone.now() + timedelta(minutes=15)
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            price_at_purchase=900.00
        )

        client = Client()
        client.force_login(self.user)

        # 1. First attempt fails
        fail_res = client.post(
            "/api/payments/verify/",
            data=json.dumps({
                "order_id": order.id,
                "payment_method": "Card",
                "simulate_status": "failed"
            }),
            content_type="application/json"
        )
        self.assertEqual(fail_res.status_code, 400)
        fail_data = fail_res.json()
        self.assertTrue(fail_data.get("can_retry"))

        order.refresh_from_db()
        self.assertIn(order.status, [Order.STATUS_PENDING, Order.STATUS_PAYMENT_PENDING])
        self.assertEqual(order.payments.count(), 1)
        self.assertEqual(order.payment.status, "Failed")

        # 2. Second attempt succeeds (retry with UPI)
        success_res = client.post(
            "/api/payments/verify/",
            data=json.dumps({
                "order_id": order.id,
                "payment_method": "UPI",
                "simulate_status": "success"
            }),
            content_type="application/json"
        )
        self.assertEqual(success_res.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PAID)
        self.assertEqual(order.payments.count(), 2)
        self.assertEqual(order.payment.status, "Success")
        self.assertEqual(order.payment.payment_method, "UPI")

    def test_structured_address_snapshot_fields(self):
        """Verify structured address snapshot fields are saved on Order."""
        addr = Address.objects.create(
            user=self.user,
            full_name="Jane Doe",
            phone_number="9123456780",
            street_address="77 Tech Blvd",
            city="Metropolis",
            state="Maharashtra",
            postal_code="400001",
            address_type="Work"
        )

        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)

        client = Client()
        client.force_login(self.user)

        res = client.post(
            "/api/orders/place_order/",
            data=json.dumps({
                "address_id": addr.id,
                "payment_method": "Card",
            }),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 201)
        order_id = res.json()["order_id"]
        order = Order.objects.get(id=order_id)

        self.assertEqual(order.recipient_name, "Jane Doe")
        self.assertEqual(order.recipient_phone, "9123456780")
        self.assertEqual(order.street_address, "77 Tech Blvd")
        self.assertEqual(order.city, "Metropolis")
        self.assertEqual(order.state, "Maharashtra")
        self.assertEqual(order.postal_code, "400001")
        self.assertEqual(order.address, addr)
        self.assertIsNotNone(order.expires_at)

    def test_structured_specifications_jsonfield_and_side_by_side_compare(self):
        """Verify specifications JSONField and side-by-side gadget comparison view."""
        self.product.specifications = {"Processor": "Intel i7", "RAM": "16GB", "Battery": "12 Hours"}
        self.product.save()
        self.assertIsInstance(self.product.specifications, dict)

        product2 = Product.objects.create(
            name="MacBook Pro 16",
            price=2000.00,
            stock=10,
            category=self.category,
            brand=self.brand,
            is_active=True,
            specifications={"Processor": "Apple M3 Pro", "RAM": "36GB", "Storage": "512GB SSD"}
        )

        client = Client()
        res = client.get(f"/products/compare/?p1={self.product.id}&p2={product2.id}")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Detailed Technical Specifications")
        self.assertContains(res, "Intel i7")
        self.assertContains(res, "Apple M3 Pro")
        self.assertContains(res, "16GB")
        self.assertContains(res, "36GB")

    def test_product_compare_rejects_different_categories(self):
        """Verify product comparison enforces same-category comparison and rejects mismatched categories."""
        other_cat = Category.objects.create(name="Smartphones")
        phone = Product.objects.create(
            name="iPhone 15 Pro",
            price=1200.00,
            stock=10,
            category=other_cat,
            brand=self.brand,
            is_active=True
        )

        client = Client()
        # Comparing Laptop vs Phone (different categories)
        res = client.get(f"/products/compare/?p1={self.product.id}&p2={phone.id}")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Different Categories Selected")
        self.assertContains(res, "Comparison is only available between gadgets in the same category")
        self.assertNotContains(res, "Detailed Technical Specifications")

    def test_product_image_gallery_model(self):
        """Verify ProductImage model links gallery images to Product."""
        gallery_img = ProductImage.objects.create(
            product=self.product,
            alt_text="Front Port Selection"
        )
        self.assertEqual(self.product.gallery_images.count(), 1)
        self.assertIn("Front Port Selection", str(gallery_img))

    def test_customer_order_cancellation_restores_stock(self):
        """Verify customer self-service cancellation updates status and restores stock."""
        initial_stock = self.product.stock
        order = Order.objects.create(
            user=self.user,
            shipping_address="100 Cancel Road",
            status=Order.STATUS_PAID,
            total_amount=1800.00
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            price_at_purchase=900.00
        )
        Product.objects.filter(id=self.product.id).update(stock=F('stock') - 2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial_stock - 2)

        client = Client()
        client.force_login(self.user)

        res = client.post(f"/orders/{order.id}/cancel/")
        self.assertEqual(res.status_code, 302)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial_stock)

    def test_payment_gateway_factory_and_adapter_pattern(self):
        """Verify PaymentGatewayFactory resolves appropriate gateway adapter."""
        from orders.payments import (
            PaymentGatewayFactory,
            SandboxPaymentGateway,
            CashOnDeliveryGateway,
            RazorpayTestGateway,
        )

        gw_card = PaymentGatewayFactory.get_gateway("Card")
        self.assertIsInstance(gw_card, SandboxPaymentGateway)

        gw_cod = PaymentGatewayFactory.get_gateway("COD")
        self.assertIsInstance(gw_cod, CashOnDeliveryGateway)

        gw_rzp = PaymentGatewayFactory.get_gateway("Razorpay")
        self.assertIsInstance(gw_rzp, RazorpayTestGateway)

    def test_strict_secret_key_validation(self):
        """Verify generate_payment_signature raises ValueError if secret key is missing."""
        from orders.payments import get_payment_secret
        with self.assertRaises(ValueError):
            get_payment_secret(secret_key="")

    def test_download_binary_pdf_invoice(self):
        """Verify download_invoice_view returns binary application/pdf with format=pdf."""
        order = Order.objects.create(
            user=self.user,
            shipping_address="789 Silicon Valley",
            status=Order.STATUS_PAID,
            total_amount=1299.00
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            price_at_purchase=1299.00
        )

        client = Client()
        client.force_login(self.user)

        res_html = client.get(f"/orders/{order.id}/invoice/")
        self.assertEqual(res_html.status_code, 200)
        self.assertIn("text/html", res_html["Content-Type"])

        res_pdf = client.get(f"/orders/{order.id}/invoice/?format=pdf")
        if res_pdf.status_code == 200:
            self.assertEqual(res_pdf["Content-Type"], "application/pdf")
            self.assertIn(f"EasyTech_Invoice_#{order.id}.pdf", res_pdf["Content-Disposition"])
            self.assertTrue(res_pdf.content.startswith(b"%PDF"))

    def test_single_product_checkout_excludes_additional_cart_items(self):
        """When purchasing a product, only the selected product is added to checkout; additional cart items are excluded."""
        cart = Cart.objects.create(user=self.user)
        product_b = Product.objects.create(
            name="Wireless Mouse",
            price=Decimal("50.00"),
            stock=15,
            category=self.category,
            brand=self.brand,
            is_active=True
        )

        item_a = CartItem.objects.create(cart=cart, product=self.product, quantity=1)  # 900
        item_b = CartItem.objects.create(cart=cart, product=product_b, quantity=2)      # 100

        client = Client()
        client.force_login(self.user)

        # 1. Access Checkout specifically for item_a
        checkout_res = client.get(f"/orders/checkout/?items={item_a.id}")
        self.assertEqual(checkout_res.status_code, 200)
        self.assertContains(checkout_res, self.product.name)
        self.assertNotContains(checkout_res, product_b.name)
        self.assertEqual(checkout_res.context["checkout_total"], Decimal("900.00"))
        self.assertEqual(len(checkout_res.context["cart_items"]), 1)

        # 2. Place order for item_a
        payload = {
            "shipping_address": "456 Silicon Alley, Bangalore - 560001",
            "payment_method": "Sandbox",
            "selected_item_ids": [item_a.id]
        }
        api_res = client.post("/api/orders/place_order/", data=payload, content_type="application/json")
        self.assertEqual(api_res.status_code, 201)
        order_id = api_res.json()["order_id"]

        order = Order.objects.get(id=order_id)
        self.assertEqual(order.items.count(), 1)
        first_order_item = order.items.first()
        self.assertIsNotNone(first_order_item)
        assert first_order_item is not None
        self.assertEqual(first_order_item.product.id, self.product.id)
        self.assertEqual(float(order.total_amount), 900.00)

        # 3. Item A is removed; Item B is STILL in user's cart
        self.assertFalse(CartItem.objects.filter(id=item_a.id).exists())
        self.assertTrue(CartItem.objects.filter(id=item_b.id).exists())
        self.assertEqual(cart.items.count(), 1)
        first_cart_item = cart.items.first()
        self.assertIsNotNone(first_cart_item)
        assert first_cart_item is not None
        self.assertEqual(first_cart_item.product.id, product_b.id)

    def test_checkout_multiple_items_requires_selection(self):
        """Direct checkout access without selection query when multiple items exist redirects to cart for explicit choice."""
        cart = Cart.objects.create(user=self.user)
        product_b = Product.objects.create(
            name="Keyboard",
            price=Decimal("80.00"),
            stock=10,
            category=self.category,
            brand=self.brand,
            is_active=True
        )
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        CartItem.objects.create(cart=cart, product=product_b, quantity=1)

        client = Client()
        client.force_login(self.user)

        res = client.get("/orders/checkout/")
        self.assertEqual(res.status_code, 302)
        redirect_url = getattr(res, "url", "")
        self.assertIn("/cart/", redirect_url)

    def test_cart_displays_only_user_chosen_products_and_recommends_based_on_preferences(self):
        """Cart displays only user chosen products; recommendations match user preferences and are not auto-added."""
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)

        # Create recommended product in same category and brand
        rec_product = Product.objects.create(
            name="Laptop Sleeve",
            price=Decimal("30.00"),
            stock=20,
            category=self.category,
            brand=self.brand,
            is_active=True
        )

        client = Client()
        client.force_login(self.user)

        res = client.get("/cart/")
        self.assertEqual(res.status_code, 200)

        # Cart table contains only user-chosen product
        self.assertEqual(res.context["cart"].items.count(), 1)
        self.assertEqual(res.context["cart"].items.first().product, self.product)

        # Recommended products contain matching item
        recommended = res.context["recommended_products"]
        self.assertTrue(any(p.id == rec_product.id for p in recommended))
        # Recommended product is NOT automatically added to cart
        self.assertFalse(cart.items.filter(product=rec_product).exists())
        self.assertEqual(cart.items.count(), 1)

        # Explicit user addition adds it to the cart
        add_res = client.post(
            "/api/cart/add_item/",
            {"product_id": rec_product.id, "quantity": 1},
            content_type="application/json"
        )
        self.assertEqual(add_res.status_code, 200)
        self.assertIn("cart_item_id", add_res.json())
        self.assertEqual(cart.items.count(), 2)
        self.assertTrue(cart.items.filter(product=rec_product).exists())

    def test_cart_recommendations_handles_null_product_in_order_items(self):
        """Verify get_recommended_products_for_user gracefully handles deleted/null products in OrderItem."""
        cart = Cart.objects.create(user=self.user)
        order = Order.objects.create(
            user=self.user,
            shipping_address="123 Test St",
            status=Order.STATUS_PAID,
            total_amount=Decimal("100.00")
        )
        # OrderItem with product=None (e.g. deleted product)
        OrderItem.objects.create(
            order=order,
            product=None,
            quantity=1,
            price_at_purchase=Decimal("100.00")
        )

        client = Client()
        client.force_login(self.user)

        res = client.get("/cart/")
        self.assertEqual(res.status_code, 200)

class ChatbotAndArchitectureTests(TestCase):
    """
    Unit and integration tests for AI Chatbot order tracking, real-time vector signals,
    custom user model compatibility, admin registration, and manager audit portal.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="customer@easytech.com",
            password="StrongPassword123!",
            name="Alex Tech"
        )
        self.other_user = User.objects.create_user(
            email="other@easytech.com",
            password="StrongPassword123!",
            name="Jordan Rivers"
        )
        self.manager = User.objects.create_user(
            email="manager@easytech.com",
            password="StrongPassword123!",
            name="Store Manager",
            is_staff=True
        )
        self.category = Category.objects.create(name="Laptops", slug="laptops")
        self.brand = Brand.objects.create(name="Framework")
        self.product = Product.objects.create(
            name="Framework Laptop 13",
            slug="framework-laptop-13",
            category=self.category,
            brand=self.brand,
            price=Decimal("89999.00"),
            stock=15,
            is_active=True,
            description="Modular Framework Laptop with Intel Core Ultra",
            specifications={"RAM": "16GB", "SSD": "512GB", "Processor": "Intel Core Ultra 7"}
        )
        self.order = Order.objects.create(
            user=self.user,
            status=Order.STATUS_SHIPPED,
            total_amount=Decimal("89999.00"),
            recipient_name="Alex Tech",
            recipient_phone="9876543210",
            street_address="10 Silicon Boulevard",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            shipping_address="10 Silicon Boulevard, Bengaluru, Karnataka 560001"
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            price_at_purchase=Decimal("89999.00")
        )

    def test_chatbot_order_tracking_authenticated_specific_order(self):
        """Verify chatbot detects order #ID query and returns live tracking status for authenticated owner."""
        from chatbot.rag_service import generate_chat_response

        query = f"Where is my order #{self.order.id}?"
        res = generate_chat_response(message=query, user=self.user)

        self.assertEqual(res.get("model"), "order-tracking")
        reply = res.get("reply", "")
        self.assertIn(f"Order Status for #{self.order.id}", reply)
        self.assertIn("Shipped", reply)
        self.assertIn("Framework Laptop 13", reply)
        self.assertIn("Bengaluru", reply)

    def test_chatbot_order_tracking_cross_account_isolation(self):
        """Verify user cannot view tracking details for an order belonging to another customer."""
        from chatbot.rag_service import generate_chat_response

        # other_user asks for self.user's order
        query = f"Track order #{self.order.id}"
        res = generate_chat_response(message=query, user=self.other_user)

        self.assertEqual(res.get("model"), "order-tracking")
        reply = res.get("reply", "")
        self.assertIn("Not Found", reply)
        self.assertNotIn("Framework Laptop 13", reply)

    def test_chatbot_order_tracking_unauthenticated_guest(self):
        """Verify unauthenticated guest is prompted to log in when inquiring about orders."""
        from chatbot.rag_service import generate_chat_response

        query = "Where is my order #1?"
        res = generate_chat_response(message=query, user=None)

        self.assertEqual(res.get("model"), "order-tracking")
        reply = res.get("reply", "")
        self.assertIn("please log in", reply.lower())

    def test_chatbot_order_tracking_recent_orders_overview(self):
        """Verify asking 'where is my order' without ID lists the customer's recent orders."""
        from chatbot.rag_service import generate_chat_response

        query = "Track my orders"
        res = generate_chat_response(message=query, user=self.user)

        self.assertEqual(res.get("model"), "order-tracking")
        reply = res.get("reply", "")
        self.assertIn(f"Order #{self.order.id}", reply)
        self.assertIn("Shipped", reply)

    def test_chatmessage_str_uses_user_name_or_email(self):
        """Verify ChatMessage string representation does not crash or display None with custom User model."""
        from chatbot.models import ChatMessage

        user_msg = ChatMessage.objects.create(
            user=self.user,
            sender="user",
            message="Show me laptops under 90k"
        )
        guest_msg = ChatMessage.objects.create(
            session_key="session1234567890",
            sender="user",
            message="Hello guest query"
        )

        self.assertIn("Alex Tech", str(user_msg))
        self.assertNotIn("None", str(user_msg))
        self.assertIn("Guest", str(guest_msg))

    def test_manager_chatbot_conversations_view_access(self):
        """Verify /manager/dashboard/conversations/ is accessible to managers and renders message logs."""
        from chatbot.models import ChatMessage

        ChatMessage.objects.create(
            user=self.user,
            sender="user",
            message="Where is my order?"
        )
        ChatMessage.objects.create(
            user=self.user,
            sender="bot",
            message="Your order #1 is Shipped."
        )

        client = Client()

        # 1. Non-staff user redirected
        client.force_login(self.user)
        denied_res = client.get("/manager/dashboard/conversations/")
        self.assertEqual(denied_res.status_code, 302)

        # 2. Manager accesses successfully
        client.force_login(self.manager)
        manager_res = client.get("/manager/dashboard/conversations/")
        self.assertEqual(manager_res.status_code, 200)
        self.assertContains(manager_res, "AI Chatbot Conversation Audit")
        self.assertContains(manager_res, "Where is my order?")

        # 3. Search filter
        search_res = client.get("/manager/dashboard/conversations/?q=Shipped")
        self.assertEqual(search_res.status_code, 200)
        self.assertContains(search_res, "Your order #1 is Shipped.")

    def test_chatbot_admin_registration(self):
        """Verify ChatMessage is registered in Django Admin site."""
        from django.contrib import admin
        from chatbot.models import ChatMessage

        self.assertIn(ChatMessage, admin.site._registry)
