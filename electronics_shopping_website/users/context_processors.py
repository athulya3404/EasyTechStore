from django.conf import settings


def allauth_settings(request):
    """Expose some settings from django-allauth in templates."""
    return {
        "ACCOUNT_ALLOW_REGISTRATION": settings.ACCOUNT_ALLOW_REGISTRATION,
    }


def profile_status(request):
    """Expose user profile and address completion status globally."""
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {
            "is_profile_incomplete": False,
            "profile_missing_fields": [],
            "has_delivery_address": False,
        }

    has_name = bool(request.user.name and request.user.name.strip())
    has_address = request.user.addresses.exists()
    is_incomplete = not (has_name and has_address)

    missing = []
    if not has_name:
        missing.append("Full Name")
    if not has_address:
        missing.append("Delivery Address (Phone, Street, City, PIN Code)")

    return {
        "is_profile_incomplete": is_incomplete,
        "profile_missing_fields": missing,
        "has_delivery_address": has_address,
    }

