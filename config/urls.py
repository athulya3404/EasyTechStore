from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views import defaults as default_views
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token

from products.views import product_compare_view, product_detail_view, product_list_view, wishlist_view, toggle_wishlist_view
from cart.views import cart_detail_view
from orders.views import verify_payment_api
from electronics_shopping_website.users.manager_views import (
    product_import,
    product_sample_template,
    product_bulk_delete,
    category_import,
    category_sample_template,
    brand_import,
    brand_sample_template,
)
from electronics_shopping_website.users.views import email_verification_sent_view


urlpatterns = [
    # ----------------------------------------------------------------------
    # CORE PAGES & UI
    # ----------------------------------------------------------------------
    path("", product_list_view, name="home"),
    path("about/", TemplateView.as_view(template_name="pages/about.html"), name="about"),
    path("products/compare/", product_compare_view, name="product_compare"),
    path("cart/", cart_detail_view, name="cart_detail"),
    path("wishlist/", wishlist_view, name="wishlist"),
    
    # ----------------------------------------------------------------------
    # APP INCLUDES (MODULAR SUB-APP ROUTING WITH NAMESPACES)
    # ----------------------------------------------------------------------
    path("orders/", include("orders.urls", namespace="orders")),
    path("products/", include("products.urls", namespace="products")),
    path("cart/", include("cart.urls", namespace="cart")),
    path("categories/", include("category.urls", namespace="category")),
    path("users/", include("electronics_shopping_website.users.urls", namespace="users")),
    path("manager/", include("electronics_shopping_website.users.manager_urls", namespace="manager")),
    path("chatbot/", include("chatbot.urls", namespace="chatbot")),
    path("accounts/confirm-email/", email_verification_sent_view, name="account_email_verification_sent"),
    path("accounts/resend-verification/", email_verification_sent_view, name="account_resend_verification"),
    path("accounts/", include("allauth.urls")),

    # ----------------------------------------------------------------------
    # PRODUCT DETAIL TOP-LEVEL ALIASES (supports lookup & reverse by slug/pk)
    # ----------------------------------------------------------------------
    path("products/<int:pk>/", product_detail_view, name="product_detail"),
    path("products/<int:pk>/", product_detail_view, name="product_detail_pk"),
    path("products/<slug:slug>/", product_detail_view, name="product_detail"),

    # ----------------------------------------------------------------------
    # TOP-LEVEL COMPATIBILITY ALIASES FOR MANAGER ACTIONS
    # ----------------------------------------------------------------------
    path("products/import/", product_import, name="product_import"),
    path("products/sample-template/", product_sample_template, name="product_sample_template"),
    path("products/bulk-delete/", product_bulk_delete, name="product_bulk_delete"),
    path("categories/import/", category_import, name="category_import"),
    path("categories/sample-template/", category_sample_template, name="category_sample_template"),
    path("brands/import/", brand_import, name="brand_import"),
    path("brands/sample-template/", brand_sample_template, name="brand_sample_template"),
    
    # ----------------------------------------------------------------------
    # WISHLIST & PAYMENT APIS
    # ----------------------------------------------------------------------
    path("api/wishlist/toggle/<int:product_id>/", toggle_wishlist_view, name="api_toggle_wishlist"),
    path("api/payments/verify/", verify_payment_api, name="api_verify_payment"),
    path("api/orders/verify_payment/", verify_payment_api, name="api_orders_verify_payment"),
    
    # ----------------------------------------------------------------------
    # ADMIN & UTILITIES
    # ----------------------------------------------------------------------
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    
    # Admin Product Creation UI
    path(
        "add-product/", 
        TemplateView.as_view(template_name="products/api_product_form.html"), 
        name="add_product"
    ),

    # Media files serving in development
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]


urlpatterns += [
    # All DRF ViewSets
    path("api/", include("config.api_router")),

    # DRF Auth Token
    path("api/auth-token/", obtain_auth_token, name="obtain_auth_token"),

    # Swagger / OpenAPI Docs
    path(
        "api/schema/",
        SpectacularAPIView.as_view(),
        name="api-schema",
    ),

    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="api-schema"),
        name="api-docs",
    ),
]

# ----------------------------------------------------------------------
# DEBUGGING & ERROR PAGES
# ----------------------------------------------------------------------
if settings.DEBUG:
    # This allows the error pages to be debugged during development
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
    
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar
        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
            *urlpatterns,
        ]