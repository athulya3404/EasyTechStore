from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _

from .forms import AddressForm
from .models import Address


@login_required
def address_create(request):
    """Create a new delivery address for the logged-in customer"""
    if request.method == "POST":
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            if address.is_default:
                Address.objects.filter(user=request.user).update(is_default=False)
            elif not Address.objects.filter(user=request.user).exists():
                address.is_default = True
            address.save()
            # If user has no name set, sync user name with address full_name
            if not request.user.name and address.full_name:
                request.user.name = address.full_name.strip()
                request.user.save(update_fields=["name"])
            messages.success(request, _("New delivery address added successfully."))
        else:
            for field, err_list in form.errors.items():
                for err in err_list:
                    field_title = "Address" if field == "__all__" else field.replace("_", " ").title()
                    messages.error(request, f"{field_title}: {err}")
    return redirect("users:detail", pk=request.user.pk)


@login_required
def address_update(request, pk):
    """Edit an existing address belonging to the logged-in customer"""
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == "POST":
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            updated = form.save(commit=False)
            if updated.is_default:
                Address.objects.filter(user=request.user).exclude(pk=pk).update(is_default=False)
            updated.save()
            if not request.user.name and updated.full_name:
                request.user.name = updated.full_name.strip()
                request.user.save(update_fields=["name"])
            messages.success(request, _("Address updated successfully."))
            return redirect("users:detail", pk=request.user.pk)
        else:
            for field, err_list in form.errors.items():
                for err in err_list:
                    field_title = "Address" if field == "__all__" else field.replace("_", " ").title()
                    messages.error(request, f"{field_title}: {err}")
    return redirect("users:detail", pk=request.user.pk)


@login_required
def address_delete(request, pk):
    """Delete an address belonging to the logged-in customer"""
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == "POST":
        was_default = address.is_default
        address.delete()
        if was_default:
            first_remaining = Address.objects.filter(user=request.user).first()
            if first_remaining:
                first_remaining.is_default = True
                first_remaining.save()
        messages.success(request, _("Address deleted successfully."))
    return redirect("users:detail", pk=request.user.pk)


@login_required
def address_set_default(request, pk):
    """Set an address as the default delivery address"""
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == "POST":
        Address.objects.filter(user=request.user).update(is_default=False)
        address.is_default = True
        address.save()
        messages.success(request, _("Default address updated successfully."))
    return redirect("users:detail", pk=request.user.pk)
