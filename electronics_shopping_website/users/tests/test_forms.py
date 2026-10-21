"""Module for all Form Tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _

from electronics_shopping_website.users.forms import UserAdminCreationForm

if TYPE_CHECKING:
    from electronics_shopping_website.users.models import User


class TestUserAdminCreationForm:
    """
    Test class for all tests related to the UserAdminCreationForm
    """

    def test_username_validation_error_msg(self, user: User):
        """
        Tests UserAdminCreation Form's unique validator functions correctly by testing:
            1) A new user with an existing username cannot be added.
            2) Only 1 error is raised by the UserCreation Form
            3) The desired error message is raised
        """

        # The user already exists,
        # hence cannot be created.
        form = UserAdminCreationForm(
            {
                "email": user.email,
                "password1": user.password,
                "password2": user.password,
            },
        )

        assert not form.is_valid()
        assert len(form.errors) == 1
        assert "email" in form.errors
        assert form.errors["email"][0] == _("This email has already been taken.")


from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser
import pytest

from electronics_shopping_website.users.forms import AddressForm
from electronics_shopping_website.users.models import Address
from electronics_shopping_website.users.context_processors import profile_status


@pytest.mark.django_db
class TestAddressFormValidation:
    def test_valid_address(self):
        data = {
            "full_name": "John Doe",
            "phone_number": "9876543210",
            "street_address": "123 Tech Street, 4th Block",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "address_type": "Home",
            "is_default": True,
        }
        form = AddressForm(data=data)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["phone_number"] == "9876543210"
        assert form.cleaned_data["postal_code"] == "560001"

    def test_phone_number_sanitization_prefixes(self):
        data = {
            "full_name": "Jane Smith",
            "phone_number": "+91 98765-43210",
            "street_address": "45 Cyber City, Tower B",
            "city": "Gurugram",
            "state": "Haryana",
            "postal_code": "122002",
            "address_type": "Work",
            "is_default": False,
        }
        form = AddressForm(data=data)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["phone_number"] == "9876543210"

    def test_phone_number_leading_zero_sanitized(self):
        data = {
            "full_name": "Jane Smith",
            "phone_number": "09876543210",
            "street_address": "45 Cyber City, Tower B",
            "city": "Gurugram",
            "state": "Haryana",
            "postal_code": "122002",
            "address_type": "Work",
            "is_default": False,
        }
        form = AddressForm(data=data)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["phone_number"] == "9876543210"

    def test_phone_number_invalid_length(self):
        data = {
            "full_name": "John Doe",
            "phone_number": "987654321",
            "street_address": "123 Tech Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "address_type": "Home",
        }
        form = AddressForm(data=data)
        assert not form.is_valid()
        assert "phone_number" in form.errors
        assert "10 digits" in form.errors["phone_number"][0]

        data["phone_number"] = "987654321000"
        form = AddressForm(data=data)
        assert not form.is_valid()
        assert "phone_number" in form.errors

    def test_phone_number_non_digits(self):
        data = {
            "full_name": "John Doe",
            "phone_number": "98765ABCD0",
            "street_address": "123 Tech Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "address_type": "Home",
        }
        form = AddressForm(data=data)
        assert not form.is_valid()
        assert "phone_number" in form.errors

    def test_postal_code_invalid(self):
        data = {
            "full_name": "John Doe",
            "phone_number": "9876543210",
            "street_address": "123 Tech Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "56000",
            "address_type": "Home",
        }
        form = AddressForm(data=data)
        assert not form.is_valid()
        assert "postal_code" in form.errors
        assert "6 digits" in form.errors["postal_code"][0]

    def test_full_name_invalid(self):
        data = {
            "full_name": "A",
            "phone_number": "9876543210",
            "street_address": "123 Tech Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "address_type": "Home",
        }
        form = AddressForm(data=data)
        assert not form.is_valid()
        assert "full_name" in form.errors

    def test_street_address_too_short(self):
        data = {
            "full_name": "John Doe",
            "phone_number": "9876543210",
            "street_address": "St",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "address_type": "Home",
        }
        form = AddressForm(data=data)
        assert not form.is_valid()
        assert "street_address" in form.errors


@pytest.mark.django_db
class TestProfileStatusContextProcessor:
    def test_anonymous_user(self):
        rf = RequestFactory()
        request = rf.get("/")
        request.user = AnonymousUser()
        res = profile_status(request)
        assert res["is_profile_incomplete"] is False
        assert res["profile_missing_fields"] == []

    def test_authenticated_user_without_address_or_name(self, user: User):
        user.name = ""
        user.save()
        rf = RequestFactory()
        request = rf.get("/")
        request.user = user
        res = profile_status(request)
        assert res["is_profile_incomplete"] is True
        assert "Full Name" in res["profile_missing_fields"]
        assert "Delivery Address (Phone, Street, City, PIN Code)" in res["profile_missing_fields"]

    def test_authenticated_user_with_name_and_address(self, user: User):
        user.name = "Verified Customer"
        user.save()
        Address.objects.create(
            user=user,
            full_name="Verified Customer",
            phone_number="9876543210",
            street_address="42 Innovation Blvd",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            address_type="Home",
            is_default=True,
        )
        rf = RequestFactory()
        request = rf.get("/")
        request.user = user
        res = profile_status(request)
        assert res["is_profile_incomplete"] is False
        assert res["profile_missing_fields"] == []

