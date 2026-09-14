"""Chatbot application configuration."""

from django.apps import AppConfig


class ChatbotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chatbot"
    verbose_name = "EasyTech AI Chatbot"

    def ready(self):
        try:
            import chatbot.signals  # noqa: F401
        except ImportError:
            pass
