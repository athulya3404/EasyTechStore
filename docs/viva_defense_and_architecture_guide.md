# EasyTechStore: Academic Viva Defense & Architecture Blueprint

This document provides external project examiners, academic guides, and viva presentation boards with a comprehensive, authoritative breakdown of the software architecture, design patterns, mathematical cryptography, concurrency guarantees, and system classification implemented across the **EasyTechStore** enterprise e-commerce platform.

---

## 1. System Stakeholders Rectification

### Critical Academic Correction:
In earlier conceptual proposal drafts, *"AI Chatbot"* was mistakenly listed as an organizational stakeholder. 
**In software engineering and UML requirements standards (IEEE 830 / ISO/IEC/IEEE 29148), an AI chatbot or automated service is a software subsystem or interface agent, NOT a project stakeholder.**

### Formal Stakeholder Classification:
1. **Registered & Guest Customers (Primary External Consumers)**:
   - Browse hardware catalog with faceted filtering (Brand, Category, Price Range).
   - Compare electronic devices side-by-side on technical specs (CPU, RAM, Display, Battery).
   - Reserve inventory with atomic 15-minute checkout timeouts.
   - Execute secure cryptographic mock or live payments with retry recovery.
   - Access self-service order cancellation and download official GST/sales tax invoices.
2. **Store Managers & Catalog Supervisors (Internal Operations)**:
   - Supervise catalog CRUD operations with single and bulk batch imports (CSV/Excel).
   - Adjust product pricing, promotional discounts, and live inventory thresholds.
   - Fulfill orders through a finite state machine: `Pending` &rarr; `Paid` &rarr; `Shipped` &rarr; `Delivered`.
   - Inspect financial analytics, revenue charts, and low-stock alerts.
3. **System Administrators & Security Officers (Infrastructure & Auditing)**:
   - Oversee database schema migrations, connection pooling, and replication integrity.
   - Manage role-based access control (RBAC), API rate-limiting, and CSRF protection.
   - Run asynchronous cron / management background cleanup workers (`cleanup_expired_orders`).

---

## 2. Functional Requirements Categorization (6 Technical Subsystems)

The complete EasyTechStore enterprise architecture is organized into six (6) decoupled, cohesive functional subsystems:

```
+-----------------------------------------------------------------------------------+
|                            EASYTECHSTORE ECOSYSTEM                                |
+-----------------------------------------------------------------------------------+
|  1. Identity & RBAC Subsystem                                                     |
|     - Custom User Model (Email Auth)  - Session & Token Authentication            |
|     - Manager Authorization Guard     - Address Book Management                   |
+-----------------------------------------------------------------------------------+
|  2. Catalog & Structured Specifications Engine                                    |
|     - JSONField Hardware Attributes   - Side-by-Side Gadget Comparator            |
|     - SEO Canonical Slugs             - Multi-Angle Image Gallery                 |
+-----------------------------------------------------------------------------------+
|  3. Cart, Wishlist & Stock Reservation Subsystem                                  |
|     - Pessimistic Row Locking         - Selective Item Checkout                   |
|     - F() Atomic Increments           - 15-Minute Expiration Engine               |
+-----------------------------------------------------------------------------------+
|  4. Two-Stage Payment Gateway Subsystem                                           |
|     - Adapter / Strategy Pattern      - HMAC-SHA256 Cryptographic Hash Check     |
|     - Multi-Attempt Payment Retry     - Zero-Leak Stock Recovery                  |
+-----------------------------------------------------------------------------------+
|  5. Order Lifecycle & Tax Invoicing Subsystem                                     |
|     - Finite State Machine Tracker    - Customer Self-Service Cancellation        |
|     - Structured Address Snapshots    - Printable Tax Invoice with INR Formatting |
+-----------------------------------------------------------------------------------+
|  6. Management Control, Batch Importers & Analytics                               |
|     - CSV / Excel Importer Parser     - Sales Reporting & Low-Stock Alerts        |
|     - Bulk Product Soft/Hard Deletes  - Order Status Transition Dispatcher        |
+-----------------------------------------------------------------------------------+
```

---

## 3. High-Scoring Viva Voce Defense Points

### Topic A: Concurrency Defense (Flash Sales & Race Conditions)
**Examiner Question:** *"What happens if 100 customers try to buy the last laptop remaining in stock at the exact same millisecond during a flash sale?"*

**Technical Defense:**
1. **The Vulnerability (Read-Modify-Write Race Condition)**:
   A naive implementation queries `product.stock`, checks `if stock > 0:`, and executes `product.stock -= 1; product.save()`. Under high concurrency, 100 concurrent threads read `stock = 1` simultaneously, all pass the validation check, and all decrement the stock, causing negative inventory (an inventory leak of -99 units).
2. **EasyTechStore's Two-Tier Defense Architecture**:
   - **Tier 1: Pessimistic Row-Level Database Locks (`select_for_update`)**:
     Inside an atomic transaction (`with transaction.atomic():`), we lock the product database rows:
     ```python
     locked_products = {
         p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids)
     }
     ```
     This executes `SELECT ... FOR UPDATE` at the database engine level (PostgreSQL / SQLite). Any concurrent transaction attempting to read or write the same row is forced into a lock wait until the active transaction completes or rolls back.
   - **Tier 2: Atomic Database-Level F() Expressions with Boundary Guards**:
     Rather than computing the new stock in Python memory, EasyTechStore delegates the decrement directly to the SQL execution engine:
     ```python
     updated = Product.objects.filter(
         id=cart_item.product.id,
         stock__gte=cart_item.quantity
     ).update(stock=F('stock') - cart_item.quantity)
     if not updated:
         raise ValueError("Stock conflict: insufficient inventory.")
     ```
     The `stock__gte=cart_item.quantity` clause ensures that even if thread contention occurs, the database will atomically reject the update if another thread decremented the stock milliseconds earlier.

---

### Topic B: Cryptographic Payment Integrity Defense (HMAC-SHA256)
**Examiner Question:** *"How does your mock/sandbox payment gateway ensure payment integrity without exposing backend secret keys to the customer's browser?"*

**Technical Defense:**
1. **The Vulnerability**:
   If a client-side JavaScript sends `{ order_id: 101, amount: 1000, status: "Success" }` to the backend, an attacker can open Chrome DevTools and alter `amount: 1` or forge payment confirmations without ever paying.
2. **EasyTechStore Cryptographic Signature Architecture**:
   - When an order is initialized on the server, the backend computes an **HMAC-SHA256** hash:
     $$\text{Signature} = \text{HMAC-SHA256}(K, \text{"order\_id:amount"})$$
     Where $K$ is `settings.SECRET_KEY` stored strictly on the server and never sent to the frontend.
   - The generated signature is transmitted to the gateway portal as a verification token.
   - When the payment outcome is simulated, the verification endpoint validates the signature:
     ```python
     def verify_payment_signature(order_id, amount, signature):
         expected = generate_payment_signature(order_id, amount)
         return hmac.compare_digest(expected, signature)
     ```
   - Notice the use of `hmac.compare_digest` instead of Python's `==` operator: this protects the system against **timing attacks**, ensuring comparison occurs in constant time.
   - Fallback Hardening: Unlike unverified systems that fall back to `'easytech-sandbox-secret'`, EasyTechStore enforces `settings.SECRET_KEY` and raises a `ValueError` if the secret key is missing.

---

### Topic C: Payment Gateway Strategy / Adapter Pattern (SOLID Architecture)
**Examiner Question:** *"Why did you create custom adapter classes instead of just writing payment if-else statements?"*

**Technical Defense:**
- Applying the **Open/Closed Principle (SOLID)**: The payment subsystem is open for extension but closed for modification.
- We defined an abstract interface:
  ```
  BasePaymentGateway (Interface)
     ├── SandboxPaymentGateway (Simulated Two-Stage Gateway)
     ├── RazorpayTestGateway (Test Mode API Adapter)
     └── CashOnDeliveryGateway (Direct Order Confirmation)
  ```
- Adding a new gateway (e.g. Stripe, Apple Pay, PayPal) only requires subclassing `BasePaymentGateway` and implementing `initiate_transaction()` and `verify_payment()`, with **zero modifications** to existing checkout views or database models.

---

### Topic D: Orphaned Inventory Prevention & Payment Retry State Machine
**Examiner Question:** *"What happens if a user's card fails or they abandon payment midway?"*

**Technical Defense:**
1. **Multi-Attempt Payment Retry**:
   - `Payment.order` is a `ForeignKey(related_name="payments")`.
   - If Attempt 1 is declined, `Payment #1` is recorded with `status='Failed'`, but `Order` is kept in `Payment_Pending`. The user is prompted with an alert to try another card, NetBanking, or UPI.
2. **15-Minute Expiration Guarantee**:
   - Every pending order receives an `expires_at = timezone.now() + timedelta(minutes=15)`.
   - The asynchronous worker command `python manage.py cleanup_expired_orders` cancels abandoned orders past 15 minutes and atomically restores reserved inventory:
     ```python
     Product.objects.filter(id=item.product_id).update(stock=F('stock') + item.quantity)
     ```
   - This eliminates inventory drains while still giving genuine buyers time to complete their purchase.
