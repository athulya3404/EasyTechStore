import os
import subprocess
import pytest
from playwright.sync_api import Browser, BrowserContext, Page

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")


def generate_django_session(is_staff: bool = False) -> str:
    """Helper to generate a valid Django session key from the running docker container."""
    filter_expr = "is_superuser=True" if is_staff else "is_superuser=False"
    cmd = [
        "docker", "compose", "-f", "docker-compose.local.yml",
        "exec", "-T", "django", "python", "manage.py", "shell", "-c",
        f"from django.contrib.sessions.backends.db import SessionStore; "
        f"from electronics_shopping_website.users.models import User; "
        f"from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY; "
        f"u = User.objects.filter({filter_expr}).first(); "
        f"s = SessionStore(); "
        f"s[SESSION_KEY] = str(u.pk) if u else '1'; "
        f"s[BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'; "
        f"s[HASH_SESSION_KEY] = u.get_session_auth_hash() if u else ''; "
        f"s.save(); "
        f"print(s.session_key)"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        return lines[-1]
    except Exception as exc:
        print(f"Warning: could not generate session via docker: {exc}")
        return "knfq86wtqrnf33wsy8t2ax275wnfi4ip"


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture
def admin_context(browser: Browser):
    """Playwright browser context pre-authenticated as Site Manager / Admin."""
    session_key = generate_django_session(is_staff=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_cookies([{
        "name": "sessionid",
        "value": session_key,
        "domain": "127.0.0.1",
        "path": "/"
    }])
    yield context
    context.close()


@pytest.fixture
def customer_context(browser: Browser):
    """Playwright browser context pre-authenticated as a customer."""
    session_key = generate_django_session(is_staff=False)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_cookies([{
        "name": "sessionid",
        "value": session_key,
        "domain": "127.0.0.1",
        "path": "/"
    }])
    yield context
    context.close()
