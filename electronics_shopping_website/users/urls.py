from django.urls import path

from .views import site_manager_created_view
from .views import user_detail_view
from .views import user_redirect_view
from .views import user_update_view

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("site-manager-created/", view=site_manager_created_view, name="site_manager_created"),
    path("<int:pk>/", view=user_detail_view, name="detail"),
]
