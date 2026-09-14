"""
Django Admin Registration for EasyTech AI Chatbot.
"""

from django.contrib import admin
from .models import ChatMessage


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "get_user_display",
        "sender_badge",
        "short_message",
        "has_products",
        "rating_badge",
        "created_at",
    )
    list_filter = ("sender", "rating", "created_at")
    search_fields = ("message", "feedback_text", "user__email", "user__name", "session_key")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
    list_per_page = 30

    @admin.display(description="User / Guest")
    def get_user_display(self, obj):
        if obj.user:
            return obj.user.name or obj.user.email
        return f"Guest ({obj.session_key[:8]})" if obj.session_key else "Guest"

    @admin.display(description="Sender")
    def sender_badge(self, obj):
        return "🤖 Bot" if obj.sender == "bot" else "👤 User"

    @admin.display(description="Rating")
    def rating_badge(self, obj):
        if obj.rating == "thumbs_up":
            return "👍 Helpful"
        elif obj.rating == "thumbs_down":
            feedback = f" ({obj.feedback_text})" if obj.feedback_text else ""
            return f"👎 Poor{feedback}"
        return "—"

    @admin.display(description="Message Preview")
    def short_message(self, obj):
        return obj.message[:80] + ("..." if len(obj.message) > 80 else "")

    @admin.display(boolean=True, description="Products Recommended")
    def has_products(self, obj):
        return bool(obj.products_json and len(obj.products_json) > 0)
