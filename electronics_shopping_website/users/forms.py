from allauth.account.forms import SignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from django.contrib.auth import forms as admin_forms
from django.forms import EmailField
from django.utils.translation import gettext_lazy as _

from .models import User


class UserAdminChangeForm(admin_forms.UserChangeForm):
    class Meta(admin_forms.UserChangeForm.Meta):
        model = User
        field_classes = {"email": EmailField}


class UserAdminCreationForm(admin_forms.AdminUserCreationForm):
    """
    Form for User Creation in the Admin Area.
    To change user signup, see UserSignupForm and UserSocialSignupForm.
    """

    class Meta(admin_forms.UserCreationForm.Meta):
        model = User
        fields = ("email",)
        field_classes = {"email": EmailField}
        error_messages = {
            "email": {"unique": _("This email has already been taken.")},
        }


class UserSignupForm(SignupForm):
    """
    Form that will be rendered on a user sign up section/screen.
    Default fields will be added automatically.
    Check UserSocialSignupForm for accounts created from social.
    """


class UserSocialSignupForm(SocialSignupForm):
    """
    Renders the form when user has signed up using social accounts.
    Default fields will be added automatically.
    See UserSignupForm otherwise.
    """


import re
from django import forms
from .models import Address


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = [
            "full_name",
            "phone_number",
            "street_address",
            "city",
            "state",
            "postal_code",
            "address_type",
            "is_default",
        ]
        widgets = {
            "full_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Full Name",
                    "required": True,
                    "minlength": "2",
                    "maxlength": "100",
                }
            ),
            "phone_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Phone Number (10 digits)",
                    "required": True,
                    "pattern": "[0-9]{10}",
                    "maxlength": "10",
                    "minlength": "10",
                    "inputmode": "numeric",
                    "title": "Please enter a 10-digit mobile number",
                }
            ),
            "street_address": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "House/Flat No., Street, Area",
                    "required": True,
                    "minlength": "5",
                    "maxlength": "255",
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "City",
                    "required": True,
                    "minlength": "2",
                    "maxlength": "100",
                }
            ),
            "state": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "State",
                    "required": True,
                    "minlength": "2",
                    "maxlength": "100",
                }
            ),
            "postal_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "PIN / Postal Code (6 digits)",
                    "required": True,
                    "pattern": "[0-9]{6}",
                    "maxlength": "6",
                    "minlength": "6",
                    "inputmode": "numeric",
                    "title": "Please enter a 6-digit PIN code",
                }
            ),
            "address_type": forms.Select(attrs={"class": "form-select"}),
            "is_default": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_full_name(self):
        full_name = self.cleaned_data.get("full_name", "").strip()
        if len(full_name) < 2:
            raise forms.ValidationError("Full Name must be at least 2 characters long.")
        if not re.match(r"^[a-zA-Z\s.'-]+$", full_name):
            raise forms.ValidationError("Full Name should contain letters and spaces only.")
        return full_name

    def clean_phone_number(self):
        raw = self.cleaned_data.get("phone_number", "").strip()
        cleaned = re.sub(r"[\s\-\(\)]", "", raw)
        if cleaned.startswith("+91") and len(cleaned) == 13:
            cleaned = cleaned[3:]
        elif cleaned.startswith("91") and len(cleaned) == 12:
            cleaned = cleaned[2:]
        elif cleaned.startswith("0") and len(cleaned) == 11:
            cleaned = cleaned[1:]

        if not (cleaned.isdigit() and len(cleaned) == 10):
            raise forms.ValidationError("Phone number must be exactly 10 digits (e.g., 9876543210).")
        return cleaned

    def clean_street_address(self):
        street = self.cleaned_data.get("street_address", "").strip()
        if len(street) < 5:
            raise forms.ValidationError("Please enter a complete address (House/Flat No., Street, Area - at least 5 characters).")
        return street

    def clean_city(self):
        city = self.cleaned_data.get("city", "").strip()
        if len(city) < 2:
            raise forms.ValidationError("City name must be at least 2 characters.")
        if not re.match(r"^[a-zA-Z\s.-]+$", city):
            raise forms.ValidationError("City name should contain letters and spaces only.")
        return city

    def clean_state(self):
        state = self.cleaned_data.get("state", "").strip()
        if len(state) < 2:
            raise forms.ValidationError("State name must be at least 2 characters.")
        if not re.match(r"^[a-zA-Z\s.-]+$", state):
            raise forms.ValidationError("State name should contain letters and spaces only.")
        return state

    def clean_postal_code(self):
        raw = self.cleaned_data.get("postal_code", "").strip()
        cleaned = re.sub(r"[\s\-]", "", raw)
        if not (cleaned.isdigit() and len(cleaned) == 6):
            raise forms.ValidationError("PIN / Postal Code must be exactly 6 digits (e.g., 560001).")
        return cleaned

