from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView
from django.views.generic import RedirectView
from django.views.generic import TemplateView
from django.views.generic import UpdateView

from electronics_shopping_website.users.models import User, Address
from electronics_shopping_website.users.forms import AddressForm

if TYPE_CHECKING:
    from django.db.models import QuerySet


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "id"
    slug_url_kwarg = "pk"

    def get_object(self, queryset: QuerySet | None = None) -> User:
        """
        Authorization check to prevent Insecure Direct Object Reference (IDOR):
        Users can only view their own profile, unless they have staff or superuser privileges.
        """
        obj = super().get_object(queryset=queryset)
        if obj != self.request.user and not (self.request.user.is_staff or self.request.user.is_superuser):
            raise PermissionDenied(_("You do not have permission to view this customer profile."))
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.get_object()
        context["addresses"] = user.addresses.all()
        context["recent_orders"] = user.orders.prefetch_related("items__product").all()[:5]
        context["total_orders_count"] = user.orders.count()
        context["wishlist_count"] = user.wishlist_items.count()
        context["address_form"] = AddressForm()
        return context


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self) -> str:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user.get_absolute_url()

    def get_object(self, queryset: QuerySet | None = None) -> User:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self) -> str:
        if self.request.user.is_staff or self.request.user.is_superuser:
            return reverse("manager:home")
        return reverse("users:detail", kwargs={"pk": self.request.user.pk})


user_redirect_view = UserRedirectView.as_view()


class SiteManagerCreatedView(TemplateView):
    """Display success page after Site Manager account is created"""
    template_name = "admin/site_manager_created.html"


site_manager_created_view = SiteManagerCreatedView.as_view()


# ==============================================================================
# CUSTOMER ADDRESS BOOK MANAGEMENT VIEWS (Delegated to address_views.py)
# ==============================================================================

from .address_views import (
    address_create,
    address_update,
    address_delete,
    address_set_default,
)

from allauth.account.models import EmailAddress


def email_verification_sent_view(request):
    """
    Renders /accounts/confirm-email/ and handles Re-send Verification requests.
    """
    email = request.GET.get("email", "").strip()
    if not email and hasattr(request, "user") and request.user.is_authenticated:
        email = request.user.email or ""

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        if not email:
            messages.error(request, _("Please enter your registered email address."))
        else:
            email_record = EmailAddress.objects.filter(email__iexact=email).first()
            if email_record:
                if email_record.verified:
                    messages.info(request, _("This email address is already verified! You can log in."))
                    return redirect("account_login")
                else:
                    try:
                        email_record.send_confirmation(request=request, signup=True)
                        messages.success(
                            request,
                            _(f"A fresh verification email has been sent to {email}. Please check your inbox and spam folder."),
                        )
                    except Exception as e:
                        messages.error(request, _(f"Error sending verification email: {e}"))
            else:
                user_match = User.objects.filter(email__iexact=email).first()
                if user_match:
                    email_record = EmailAddress.objects.create(
                        user=user_match,
                        email=user_match.email,
                        verified=False,
                        primary=True,
                    )
                    try:
                        email_record.send_confirmation(request=request, signup=True)
                        messages.success(
                            request,
                            _(f"A fresh verification email has been sent to {email}. Please check your inbox and spam folder."),
                        )
                    except Exception as e:
                        messages.error(request, _(f"Error sending verification email: {e}"))
                else:
                    messages.info(
                        request,
                        _(f"If an account exists with {email}, a verification email has been sent."),
                    )

        return redirect(f"{reverse('account_email_verification_sent')}?email={email}")

    return render(
        request,
        "account/verification_sent.html",
        {
            "email": email,
        },
    )

