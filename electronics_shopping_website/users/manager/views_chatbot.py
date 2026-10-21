"""
Manager Dashboard: AI Chatbot Conversation Monitoring Views
Allows store administrators and managers to audit customer-AI chats,
analyze common queries, inspect bot responses, and track catalog recommendation patterns.
"""

from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from chatbot.models import ChatMessage
from .decorators import manager_required


@manager_required
def manager_chatbot_conversations(request):
    """
    GET /manager/dashboard/conversations/
    Display paginated log of all customer AI chatbot interactions.
    """
    search_query = request.GET.get("q", "").strip()
    sender_filter = request.GET.get("sender", "").strip()
    date_filter = request.GET.get("date", "").strip()

    queryset = ChatMessage.objects.select_related("user").order_by("-created_at")

    # Search filter (email, name, session_key, message)
    if search_query:
        queryset = queryset.filter(
            Q(message__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(user__name__icontains=search_query)
            | Q(session_key__icontains=search_query)
        )

    # Sender filter (user or bot)
    if sender_filter in ("user", "bot"):
        queryset = queryset.filter(sender=sender_filter)

    # Date filter
    now = timezone.now()
    if date_filter == "today":
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        queryset = queryset.filter(created_at__gte=start_of_day)
    elif date_filter == "7days":
        queryset = queryset.filter(created_at__gte=now - timedelta(days=7))
    elif date_filter == "30days":
        queryset = queryset.filter(created_at__gte=now - timedelta(days=30))

    # Overall Summary Statistics
    total_messages = ChatMessage.objects.count()
    user_queries_count = ChatMessage.objects.filter(sender="user").count()
    bot_replies_count = ChatMessage.objects.filter(sender="bot").count()
    recommendation_messages_count = (
        ChatMessage.objects.filter(sender="bot")
        .exclude(products_json=[])
        .exclude(products_json__isnull=True)
        .count()
    )

    # Pagination
    paginator = Paginator(queryset, 25)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "messages": page_obj,
        "search_query": search_query,
        "sender_filter": sender_filter,
        "date_filter": date_filter,
        "total_messages": total_messages,
        "user_queries_count": user_queries_count,
        "bot_replies_count": bot_replies_count,
        "recommendation_messages_count": recommendation_messages_count,
        "active_tab": "chatbot_conversations",
    }
    return render(request, "manager/chatbot_conversations.html", context)
