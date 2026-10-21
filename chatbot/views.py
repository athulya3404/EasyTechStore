"""
Views for the RAG-powered Chatbot in EasyTech Store.
"""

import json
import logging
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.contrib.admin.views.decorators import staff_member_required

from .rag_service import generate_chat_response as answer_user_query, index_products, get_chroma_collection
from .models import ChatMessage

logger = logging.getLogger(__name__)


def _get_or_create_session_key(request):
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ""


@csrf_exempt
@require_POST
def chat_api_view(request):
    """
    POST /chatbot/api/chat/
    Body: JSON {"message": "...", "top_k": 3}
    Returns: JSON {"reply": "...", "products": [...], "status": "success"}
    Saves message and reply in ChatMessage database.
    Rate-limited to 20 requests per minute per IP to protect LLM quota.
    """
    # Rate Limiting Check (20 requests per minute per client IP)
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "unknown")
    rate_key = f"chatbot_rate_{client_ip}"
    request_count = cache.get(rate_key, 0)
    if request_count >= 20:
        return JsonResponse(
            {
                "status": "error",
                "error": "Rate limit exceeded. Please wait a moment before sending more messages.",
                "reply": "You are sending messages too quickly. Please wait a minute before asking another question."
            },
            status=429
        )
    cache.set(rate_key, request_count + 1, timeout=60)

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)

    user_query = data.get("message", "").strip()
    if not user_query:
        return JsonResponse({"error": "Query 'message' cannot be empty"}, status=400)

    user = request.user if request.user.is_authenticated else None
    session_key = _get_or_create_session_key(request)

    # Fetch recent conversation turns for context
    history = []
    if user:
        recent_msgs = ChatMessage.objects.filter(user=user).order_by("-created_at")[:6]
    else:
        recent_msgs = ChatMessage.objects.filter(session_key=session_key).order_by("-created_at")[:6]

    for m in reversed(recent_msgs):
        history.append({
            "role": "user" if m.sender == "user" else "assistant",
            "content": m.message,
        })

    # Save user message
    ChatMessage.objects.create(
        user=user,
        session_key=session_key,
        sender="user",
        message=user_query,
    )

    try:
        result = answer_user_query(message=user_query, history=history, user=user)
        reply_text = result.get("reply", "")
        products = result.get("products", [])

        # Save assistant message
        bot_msg = ChatMessage.objects.create(
            user=user,
            session_key=session_key,
            sender="bot",
            message=reply_text,
            products_json=products,
        )

        return JsonResponse({
            "status": "success",
            "reply": reply_text,
            "products": products,
            "message_id": bot_msg.id,
            "model": result.get("model", ""),
        })
    except Exception as exc:
        logger.exception("Error processing chatbot query")
        return JsonResponse({
            "status": "error",
            "reply": "Sorry, I encountered an issue processing your request. Please try again.",
            "error": str(exc),
        }, status=500)


@require_GET
def chat_history_api_view(request):
    """
    GET /chatbot/api/history/
    Returns chat history for the currently signed-in user (or guest session).
    """
    user = request.user if request.user.is_authenticated else None
    session_key = _get_or_create_session_key(request)

    if user:
        messages_qs = ChatMessage.objects.filter(user=user).order_by("created_at")
    else:
        messages_qs = ChatMessage.objects.filter(session_key=session_key).order_by("created_at")

    messages_data = [
        {
            "id": m.id,
            "sender": m.sender,
            "message": m.message,
            "products": m.products_json or [],
            "rating": m.rating,
            "feedback": m.feedback_text,
            "created_at": m.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for m in messages_qs[:50]
    ]

    return JsonResponse({
        "status": "success",
        "is_authenticated": user is not None,
        "username": (user.name or user.email) if user else None,
        "history": messages_data,
    })


@csrf_exempt
@require_POST
def chat_feedback_api_view(request):
    """
    POST /chatbot/api/feedback/
    Body: JSON {"message_id": 123, "rating": "thumbs_up" | "thumbs_down" | "clear", "feedback": "optional"}
    Records customer satisfaction rating for bot responses.
    """
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"status": "error", "error": "Invalid JSON body"}, status=400)

    message_id = data.get("message_id")
    rating = (data.get("rating") or "").strip().lower()
    feedback_text = (data.get("feedback") or "").strip()

    if not message_id:
        return JsonResponse({"status": "error", "error": "Missing 'message_id'"}, status=400)

    if rating not in ("thumbs_up", "thumbs_down", "clear"):
        return JsonResponse({
            "status": "error",
            "error": "Rating must be 'thumbs_up', 'thumbs_down', or 'clear'",
        }, status=400)

    try:
        msg = ChatMessage.objects.get(id=message_id, sender="bot")
    except ChatMessage.DoesNotExist:
        return JsonResponse({"status": "error", "error": "Bot message not found"}, status=404)

    msg.rating = None if rating == "clear" else rating
    if feedback_text:
        msg.feedback_text = feedback_text
    msg.save(update_fields=["rating", "feedback_text"])

    logger.info("Recorded feedback for message #%s: rating=%s", msg.id, msg.rating)
    return JsonResponse({
        "status": "success",
        "message_id": msg.id,
        "rating": msg.rating,
        "feedback": msg.feedback_text,
    })


@csrf_exempt
@require_POST
def index_catalog_api_view(request):
    """
    POST /chatbot/api/index/
    Trigger re-indexing of products into the vector database.
    """
    try:
        result = index_products()
        return JsonResponse({
            "status": "success",
            "message": f"Indexed {result.get('indexed', 0)} products into vector store.",
            "details": result,
        })
    except Exception as exc:
        logger.exception("Error indexing catalog")
        return JsonResponse({
            "status": "error",
            "message": str(exc),
        }, status=500)


@require_GET
def chatbot_status_api_view(request):
    """
    GET /chatbot/api/status/
    Healthcheck endpoint to verify ChromaDB and Ollama readiness.
    """
    collection = get_chroma_collection()
    count = 0
    chroma_ready = False
    if collection is not None:
        try:
            count = collection.count()
            chroma_ready = True
        except Exception:
            chroma_ready = False

    return JsonResponse({
        "status": "online",
        "chroma_ready": chroma_ready,
        "indexed_products": count,
    })


@csrf_exempt
def stream_chat_api_view(request):
    """
    GET or POST /chatbot/api/stream/
    Streams AI tokens via Server-Sent Events (SSE) for a real-time typewriter experience.
    """
    if request.method == "POST":
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
            user_query = body.get("message", "").strip()
        except Exception:
            user_query = ""
    else:
        user_query = request.GET.get("message", "").strip()

    if not user_query:
        return JsonResponse({"error": "Empty message"}, status=400)

    user = request.user if request.user.is_authenticated else None

    def event_stream():
        from .rag_service import (
            check_order_tracking_intent,
            retrieve_relevant_products,
            get_llm_client_and_models,
        )
        tracking_res = check_order_tracking_intent(user_query, user=user)
        if tracking_res:
            yield f"data: {json.dumps({'type': 'content', 'token': tracking_res.get('reply', '')})}\n\n"
            yield f"data: {json.dumps({'type': 'products', 'products': []})}\n\n"
            yield "data: [DONE]\n\n"
            return

        products = retrieve_relevant_products(user_query, n_results=6)
        if products:
            yield f"data: {json.dumps({'type': 'products', 'products': products})}\n\n"

        try:
            client, primary_model, fallback_model = get_llm_client_and_models()

            context_items = "\n".join([
                f"{i}. Product: {p.get('name')} | Brand: {p.get('brand')} | Price: ₹{float(p.get('price', 0)):,.2f} | Stock: {p.get('stock')}"
                for i, p in enumerate(products, start=1)
            ]) if products else "No matching catalog products."

            system_prompt = f"""You are 'EasyTech Assistant', the official AI shopping consultant for EasyTech Store.
Ground every statement strictly in the STORE CATALOG DATA:
{context_items}
FEW-SHOT EXAMPLES:
Customer: 'Do you have iPad under 35k?' -> Assistant: 'Yes, Apple iPad 9th Gen is available for ₹30,900 with A13 Bionic chip.'
Customer: 'Dell laptop with RTX 4060 under 50k' -> Assistant: 'We do not have a Dell RTX 4060 under ₹50,000, but offer Asus TUF Gaming F15 starting at ₹54,990.'
Keep replies concise, friendly, and quote prices in INR (₹)."""

            try:
                stream = client.chat.completions.create(
                    model=primary_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_query}
                    ],
                    temperature=0.0,
                    max_tokens=350,
                    stream=True,
                )
            except Exception:
                stream = client.chat.completions.create(
                    model=fallback_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_query}
                    ],
                    temperature=0.0,
                    max_tokens=350,
                    stream=True,
                )

            for chunk in stream:
                token = chunk.choices[0].delta.content or ""
                if token:
                    yield f"data: {json.dumps({'type': 'content', 'token': token})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'content', 'token': 'Here are the best matching items from our store catalog.'})}\n\n"

        yield "data: [DONE]\n\n"

    from django.http import StreamingHttpResponse
    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response

