from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CategoryForm
from .models import Category


def category_list(request):
    """
    Return all categories.
    """

    categories = Category.objects.all()

    return render(
        request,
        "category/category_list.html",
        {
            "categories": categories,
        },
    )


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


def category_delete(request, pk):
    """
    Delete a category.
    """

    category = get_object_or_404(
        Category,
        pk=pk,
    )

    if request.method == "POST":
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