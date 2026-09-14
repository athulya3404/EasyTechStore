from django.db import models
from django.conf import settings


class ChatMessage(models.Model):
    """
    Stores chatbot conversation messages for logged-in or guest users.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="chat_messages",
    )
    session_key = models.CharField(max_length=64, blank=True, default="", db_index=True)
    sender = models.CharField(max_length=16, choices=(("user", "User"), ("bot", "Bot")), default="user")
    message = models.TextField()
    products_json = models.JSONField(blank=True, null=True, default=list)
    rating = models.CharField(
        max_length=16,
        choices=(("thumbs_up", "Thumbs Up"), ("thumbs_down", "Thumbs Down")),
        null=True,
        blank=True,
        db_index=True,
    )
    feedback_text = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        user_display = (self.user.name or self.user.email) if self.user else f"Guest ({self.session_key[:8]})"
        return f"[{self.sender}] {user_display}: {self.message[:30]}"
