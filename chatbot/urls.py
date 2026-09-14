from django.urls import path
from . import views

app_name = "chatbot"

urlpatterns = [
    path("api/chat/", views.chat_api_view, name="api_chat"),
    path("api/stream/", views.stream_chat_api_view, name="api_stream"),
    path("api/history/", views.chat_history_api_view, name="api_history"),
    path("api/feedback/", views.chat_feedback_api_view, name="api_feedback"),
    path("api/index/", views.index_catalog_api_view, name="api_index"),
    path("api/status/", views.chatbot_status_api_view, name="api_status"),
]
