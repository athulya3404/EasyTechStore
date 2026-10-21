import os
import pytest
from playwright.sync_api import Page, expect

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


class TestNavbarAndHeaderButtons:
    """Validate all interactive buttons and UX elements in the header and navbar."""

    def test_logo_brand_visibility_and_click(self, page: Page, base_url: str):
        page.goto(base_url)
        logo = page.locator("a.navbar-brand img")
        expect(logo).to_be_visible()
        # Verify EasyTech logo is loaded properly
        logo.click()
        expect(page).to_have_url(f"{base_url}/")

    def test_header_search_button(self, page: Page, base_url: str):
        page.goto(base_url)
        search_input = page.locator("#headerForm input[name='q']")
        expect(search_input).to_be_visible()
        search_input.fill("Laptop")
        
        search_btn = page.locator("#headerForm button[type='submit']")
        expect(search_btn).to_be_visible()
        search_btn.click()
        
        # Verify redirect with query parameter
        expect(page).to_have_url(f"{base_url}/?q=Laptop#shop-section")

    def test_wishlist_and_cart_buttons(self, customer_context, base_url: str):
        """Test wishlist and cart buttons with authenticated customer session."""
        page = customer_context.new_page()
        page.goto(base_url)
        wishlist_btn = page.locator(".header-action-details a[href*='wishlist']")
        expect(wishlist_btn).to_be_visible()
        
        cart_btn = page.locator(".header-action-details a[href='/cart/']")
        expect(cart_btn).to_be_visible()
        cart_btn.click()
        expect(page).to_have_url(f"{base_url}/cart/")

    def test_manager_dashboard_badge_for_staff(self, admin_context, base_url: str):
        page = admin_context.new_page()
        page.goto(base_url)
        dashboard_badge = page.locator(".header-action-details a[href*='manager']")
        expect(dashboard_badge).to_be_visible()
        expect(dashboard_badge).to_contain_text("Dashboard")
        
        # Click dashboard button and verify navigation to manager dashboard
        dashboard_badge.click()
        expect(page).to_have_url(f"{base_url}/manager/dashboard/home/")
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "staff_dashboard_button.png"))


class TestProductDetailInteractions:
    """Validate buttons, quantity steppers, cart & buy now triggers on product detail pages."""

    def test_quantity_stepper_and_add_to_cart(self, customer_context, base_url: str):
        page = customer_context.new_page()
        # Use existing product ID from database
        page.goto(f"{base_url}/products/12222/")
        
        # Quantity Steppers
        qty_input = page.locator("#productQty")
        if qty_input.count() > 0:
            expect(qty_input).to_have_value("1")
            
            # Click increment button '+'
            plus_btn = page.locator("button[onclick='incrementQty()']")
            plus_btn.click()
            expect(qty_input).to_have_value("2")
            
            # Click decrement button '-'
            minus_btn = page.locator("button[onclick='decrementQty()']")
            minus_btn.click()
            expect(qty_input).to_have_value("1")

        # Verify Add to Cart button
        add_to_cart_btn = page.locator("button:has-text('Add to Cart')")
        expect(add_to_cart_btn).to_be_visible()
        
        # Verify Buy Now button exists with Amazon-style styling
        buy_now_btn = page.locator("button:has-text('Buy Now')")
        expect(buy_now_btn).to_be_visible()
        
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "product_detail_buttons.png"))


class TestCartAndCheckoutButtons:
    """Validate interactive elements on the cart page."""

    def test_cart_empty_state_or_table_actions(self, customer_context, base_url: str):
        page = customer_context.new_page()
        page.goto(f"{base_url}/cart/")
        
        # Verify page header
        expect(page.locator("h1:has-text('Shopping Cart')")).to_be_visible()
        
        # If empty cart state
        browse_btn = page.locator("a:has-text('Browse Electronics')")
        proceed_btn = page.locator("#proceedToCheckoutBtn")
        
        if browse_btn.is_visible():
            expect(browse_btn).to_be_visible()
            browse_btn.click()
            expect(page).to_have_url(f"{base_url}/")
        elif proceed_btn.is_visible():
            expect(proceed_btn).to_be_visible()
            expect(proceed_btn).to_contain_text("Proceed to Checkout")


class TestManagerDashboardSidebarAndActions:
    """Validate manager console buttons, sidebar navigation, and quick links."""

    def test_manager_sidebar_navigation_and_storefront_button(self, admin_context, base_url: str):
        page = admin_context.new_page()
        page.goto(f"{base_url}/manager/dashboard/home/")
        
        # Verify Manager sidebar brand
        brand_title = page.locator(".sidebar-brand-title")
        expect(brand_title).to_be_visible()
        expect(brand_title).to_contain_text("MANAGER")
        
        # Verify View Storefront button
        storefront_link = page.locator(".sidebar-link:has-text('View Storefront')")
        expect(storefront_link).to_be_visible()
        
        # Verify Quick Action Buttons
        add_product_btn = page.locator(".btn-primary:has-text('Add Product')")
        if add_product_btn.count() > 0:
            expect(add_product_btn.first).to_be_visible()
            
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "manager_dashboard_unified.png"))
