from django.urls import path

from .views import (
    site_manager_created_view,
    user_detail_view,
    user_redirect_view,
    user_update_view,
    address_create,
    address_update,
    address_delete,
    address_set_default,
)

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("site-manager-created/", view=site_manager_created_view, name="site_manager_created"),
    path("<int:pk>/", view=user_detail_view, name="detail"),
    
    # Customer Address Management
    path("addresses/add/", view=address_create, name="address_create"),
    path("addresses/<int:pk>/edit/", view=address_update, name="address_edit"),
    path("addresses/<int:pk>/delete/", view=address_delete, name="address_delete"),
    path("addresses/<int:pk>/set-default/", view=address_set_default, name="address_set_default"),
]
