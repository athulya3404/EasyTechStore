from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views import defaults as default_views
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token

# Import your custom views here
from products.views import product_detail_view, product_list_view
from cart.views import cart_detail_view


urlpatterns = [
    # ----------------------------------------------------------------------
    # CORE PAGES & UI
    # ----------------------------------------------------------------------
    path("", product_list_view, name="home"),
    path("about/", TemplateView.as_view(template_name="pages/about.html"), name="about"),
    path("products/<int:pk>/", product_detail_view, name="product_detail"),
    path("cart/", cart_detail_view, name="cart_detail"),
    path("orders/", include("orders.urls")),
   
    
    # ----------------------------------------------------------------------
    # APP INCLUDES
    # ----------------------------------------------------------------------
    path("categories/", include("category.urls")),
    
    # ----------------------------------------------------------------------
    # USER MANAGEMENT & AUTHENTICATION
    # ----------------------------------------------------------------------
    path("users/", include("electronics_shopping_website.users.urls", namespace="users")),
    path("manager/", include("electronics_shopping_website.users.manager_urls", namespace="manager")),
    path("accounts/", include("allauth.urls")),
    
    # ----------------------------------------------------------------------
    # ADMIN & UTILITIES
    # ----------------------------------------------------------------------
    # Django Admin, use {% url 'admin:index' %}
    path("dashboard/", include("dashboard.urls", namespace="dashboard")),
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