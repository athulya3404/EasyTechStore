from django.urls import path

from . import views
from electronics_shopping_website.users.manager_views import category_import


app_name = "category"


urlpatterns = [
    path(
        "",
        views.category_list,
        name="list",
    ),

    path(
        "add/",
        views.category_create,
        name="create",
    ),

    path(
        "import/",
        category_import,
        name="import",
    ),

    path(
        "<int:pk>/update/",
        views.category_update,
        name="update",
    ),

    path(
        "<int:pk>/delete/",
        views.category_delete,
        name="delete",
    ),

    path(
        "<slug:slug>/",
        views.category_detail,
        name="detail",
    ),

    path(
        "id/<int:pk>/",
        views.category_detail,
        name="detail_by_id",
    ),
]