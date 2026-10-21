import os
import sys
import time
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from django.core.cache import cache
from products.models import Product, Category, Brand
from orders.models import Order
from chatbot.rag_service import generate_chat_response

User = get_user_model()

print("=" * 70)
print("COMPREHENSIVE WEBSITE HEALTH & PERFORMANCE AUDIT")
print("=" * 70)

results = []

def record(category, name, status, time_taken, details=""):
    results.append({
        "category": category,
        "name": name,
        "status": status,
        "time_ms": round(time_taken * 1000, 2),
        "details": details
    })
    symbol = "✅" if status == "PASS" else "❌"
    print(f"{symbol} [{category}] {name:<35} | {status} ({round(time_taken * 1000, 1)}ms) {details}")

# 1. Infrastructure Checks
print("\n--- 1. INFRASTRUCTURE & BACKEND SERVICES ---")

# Database
t0 = time.time()
try:
    p_count = Product.objects.count()
    o_count = Order.objects.count()
    u_count = User.objects.count()
    record("INFRA", "PostgreSQL Database", "PASS", time.time() - t0, f"Products: {p_count}, Orders: {o_count}, Users: {u_count}")
except Exception as e:
    record("INFRA", "PostgreSQL Database", "FAIL", time.time() - t0, str(e))

# Redis Cache
t0 = time.time()
try:
    cache.set("audit_health_check", "ok", 60)
    val = cache.get("audit_health_check")
    if val == "ok":
        record("INFRA", "Redis Cache / Session Store", "PASS", time.time() - t0, "Read/write verified")
    else:
        record("INFRA", "Redis Cache / Session Store", "FAIL", time.time() - t0, f"Unexpected cache value: {val}")
except Exception as e:
    record("INFRA", "Redis Cache / Session Store", "FAIL", time.time() - t0, str(e))

# Groq AI Service
t0 = time.time()
try:
    ai_resp = generate_chat_response("Hello")
    reply = ai_resp.get("reply", "") if isinstance(ai_resp, dict) else str(ai_resp)
    if reply:
        record("INFRA", "Groq AI LLM Service", "PASS", time.time() - t0, f"Sample output: {reply[:35]}...")
    else:
        record("INFRA", "Groq AI LLM Service", "FAIL", time.time() - t0, "Empty response")
except Exception as e:
    record("INFRA", "Groq AI LLM Service", "FAIL", time.time() - t0, str(e))


# 2. Public Endpoints
print("\n--- 2. PUBLIC STOREFRONT PAGES ---")
client = Client()

public_urls = [
    ("Home Page", "/"),
    ("Product Catalog", "/products/"),
    ("Product Compare", "/products/compare/"),
    ("Shopping Cart", "/cart/"),
    ("Search Autocomplete API", "/products/api/autocomplete/?q=phone"),
    ("Login Page", "/accounts/login/"),
    ("Signup Page", "/accounts/signup/"),
    ("Password Reset", "/accounts/password/reset/"),
    ("Static Placeholder Image", "/static/images/placeholder.png"),
]

# Add a real product detail page if products exist
first_product = Product.objects.filter(is_active=True).first()
if first_product:
    prod_name = getattr(first_product, 'name', 'Product')
    if hasattr(first_product, 'slug') and first_product.slug:
        public_urls.insert(2, (f"Product Detail ({prod_name[:20]})", f"/products/{first_product.slug}/"))
    else:
        public_urls.insert(2, (f"Product Detail ({prod_name[:20]})", f"/products/{first_product.pk}/"))

for name, url in public_urls:
    t0 = time.time()
    try:
        resp = client.get(url, HTTP_HOST="easystore1.me")
        duration = time.time() - t0
        if resp.status_code in (200, 302):
            record("PUBLIC", name, "PASS", duration, f"HTTP {resp.status_code}")
        else:
            record("PUBLIC", name, "FAIL", duration, f"HTTP {resp.status_code}")
    except Exception as e:
        record("PUBLIC", name, "FAIL", time.time() - t0, str(e))

# 3. Authenticated Customer Pages
print("\n--- 3. AUTHENTICATED CUSTOMER PAGES ---")
customer_user = User.objects.filter(is_staff=False, is_superuser=False).first()
if customer_user:
    customer_client = Client()
    customer_client.force_login(customer_user)
    
    customer_urls = [
        ("Customer Profile Redirect", "/users/~redirect/"),
        ("Customer Orders List", "/orders/my-orders/"),
        ("Customer Checkout", "/orders/checkout/"),
    ]

    # Add a customer order details page if available
    customer_order = Order.objects.filter(user=customer_user).first()
    if customer_order:
        customer_urls.append((f"Order Confirmation #{customer_order.pk}", f"/orders/confirmation/{customer_order.pk}/"))

    for name, url in customer_urls:
        t0 = time.time()
        try:
            resp = customer_client.get(url, HTTP_HOST="easystore1.me")
            duration = time.time() - t0
            if resp.status_code in (200, 302):
                record("CUSTOMER", name, "PASS", duration, f"HTTP {resp.status_code}")
            else:
                record("CUSTOMER", name, "FAIL", duration, f"HTTP {resp.status_code}")
        except Exception as e:
            record("CUSTOMER", name, "FAIL", time.time() - t0, str(e))
else:
    print("No non-staff customer user found in DB.")

# 4. Manager Portal Pages
print("\n--- 4. MANAGER & STAFF PORTAL PAGES ---")
manager_user = User.objects.filter(is_staff=True).first() or User.objects.filter(is_superuser=True).first()
if manager_user:
    manager_client = Client()
    manager_client.force_login(manager_user)
    
    manager_urls = [
        ("Manager Dashboard Home", "/manager/dashboard/home/"),
        ("Manager Products List", "/manager/dashboard/products/"),
        ("Manager Product Add Form", "/manager/dashboard/products/add/"),
        ("Manager Product Import", "/manager/dashboard/products/import/"),
        ("Manager Categories List", "/manager/dashboard/categories/"),
        ("Manager Brands List", "/manager/dashboard/brands/"),
        ("Manager Inventory View", "/manager/dashboard/inventory/"),
        ("Manager Orders List", "/manager/dashboard/orders/"),
        ("Manager Sales Reports", "/manager/dashboard/reports/"),
        ("Manager Customer Management", "/manager/dashboard/users/"),
        ("Manager Chatbot Monitor", "/manager/dashboard/conversations/"),
    ]
    
    for name, url in manager_urls:
        t0 = time.time()
        try:
            resp = manager_client.get(url, HTTP_HOST="easystore1.me")
            duration = time.time() - t0
            if resp.status_code in (200, 302):
                record("MANAGER", name, "PASS", duration, f"HTTP {resp.status_code}")
            else:
                record("MANAGER", name, "FAIL", duration, f"HTTP {resp.status_code}")
        except Exception as e:
            record("MANAGER", name, "FAIL", time.time() - t0, str(e))
else:
    print("No manager/staff user found.")

# 5. Core APIs
print("\n--- 5. CORE APIS ---")
# Chatbot API
t0 = time.time()
try:
    resp = client.post("/chatbot/api/chat/", data='{"message": "Do you have phones?"}', content_type="application/json", HTTP_HOST="easystore1.me")
    duration = time.time() - t0
    if resp.status_code == 200:
        reply = resp.json().get('reply', '')
        record("API", "Chatbot Query API", "PASS", duration, f"HTTP 200: {reply[:30]}...")
    else:
        record("API", "Chatbot Query API", "FAIL", duration, f"HTTP {resp.status_code}")
except Exception as e:
    record("API", "Chatbot Query API", "FAIL", time.time() - t0, str(e))

# Autocomplete API
t0 = time.time()
try:
    resp = client.get("/products/api/autocomplete/?q=a", HTTP_HOST="easystore1.me")
    duration = time.time() - t0
    if resp.status_code == 200:
        record("API", "Product Autocomplete API", "PASS", duration, f"HTTP 200: {len(resp.json().get('results', []))} items found")
    else:
        record("API", "Product Autocomplete API", "FAIL", duration, f"HTTP {resp.status_code}")
except Exception as e:
    record("API", "Product Autocomplete API", "FAIL", time.time() - t0, str(e))

print("\n" + "=" * 70)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
print(f"AUDIT SUMMARY: {passed} PASSED, {failed} FAILED (Total: {len(results)})")
print("=" * 70)
