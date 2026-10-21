from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def manager_required(view_func):
    """Decorator: Require user to be a site manager (is_staff=True) or superadmin"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('account_login')
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, "You do not have permission to access the manager dashboard.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


def superadmin_required(view_func):
    """Decorator: Require user to be a superadmin (is_superuser=True)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('account_login')
        if not request.user.is_superuser:
            messages.error(request, "You do not have permission to access this page.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper
