from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from electronics_shopping_website.users.manager_views import manager_required
from .forms import CategoryForm
from .models import Category


def category_list(request):
    categories = Category.objects.filter(is_active=True)

    return render(
        request,
        "category/category_list.html",
        {
            "categories": categories,
        },
    )


@login_required
@manager_required
def category_create(request):
    """
    Create a new category.
    """

    if request.method == "POST":
        form = CategoryForm(request.POST)

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Category created successfully.",
            )

            return redirect("category:list")

    else:
        form = CategoryForm()

    return render(
        request,
        "category/category_form.html",
        {
            "form": form,
            "title": "Add Category",
        },
    )


@login_required
@manager_required
def category_update(request, pk):
    """
    Update an existing category.
    """

    category = get_object_or_404(
        Category,
        pk=pk,
    )

    if request.method == "POST":
        form = CategoryForm(
            request.POST,
            instance=category,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Category updated successfully.",
            )

            return redirect("category:list")

    else:
        form = CategoryForm(
            instance=category,
        )

    return render(
        request,
        "category/category_form.html",
        {
            "form": form,
            "title": "Update Category",
            "category": category,
        },
    )


@login_required
@manager_required
def category_delete(request, pk):
    """
    Delete a category.
    """

    category = get_object_or_404(
        Category,
        pk=pk,
    )

    if request.method == "POST":
        if category.products.exists():
            messages.error(
                request,
                f"Cannot delete category '{category.name}' because it contains active products.",
            )
            return redirect("category:list")

        category.delete()

        messages.success(
            request,
            "Category deleted successfully.",
        )

        return redirect("category:list")

    return render(
        request,
        "category/category_confirm_delete.html",
        {
            "category": category,
        },
    )


def category_detail(request, slug=None, pk=None):
    """
    Renders dedicated category storefront with products filtered by this category.
    """
    if slug:
        category = get_object_or_404(Category, slug=slug)
    else:
        category = get_object_or_404(Category, pk=pk)

    products = category.products.filter(is_active=True).select_related("brand")
    return render(
        request,
        "category/category_detail.html",
        {
            "category": category,
            "products": products,
        },
    )