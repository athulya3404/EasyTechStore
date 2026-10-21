import json
import sys
from unittest.mock import patch, MagicMock

# Ensure openai module is available in mock test environment
if "openai" not in sys.modules:
    sys.modules["openai"] = MagicMock()
    sys.modules["openai"].OpenAI = MagicMock()
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from category.models import Category
from products.models import Product, Brand
from orders.models import Order, OrderItem
from chatbot.models import ChatMessage
from chatbot.rag_service import (
    condense_query_with_history,
    generate_chat_response,
    semantic_product_search,
    check_order_tracking_intent,
    format_order_tracking_details,
    retrieve_historical_chat_knowledge,
    OLLAMA_MODEL,
    OLLAMA_FALLBACK_MODEL,
)
from chatbot.admin import ChatMessageAdmin
from django.contrib.admin.sites import AdminSite

from typing import Any
User: Any = get_user_model()


class ChatbotEnhancementsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="chatuser@example.com",
            password="securepassword123",
            name="Chat Tester"
        )

    def test_chat_message_rating_fields(self):
        """Verify rating and feedback_text fields on ChatMessage."""
        msg = ChatMessage.objects.create(
            sender="bot",
            message="Here are some laptops.",
            rating="thumbs_up",
            feedback_text="Very helpful!"
        )
        msg.refresh_from_db()
        self.assertEqual(msg.rating, "thumbs_up")
        self.assertEqual(msg.feedback_text, "Very helpful!")

    def test_chat_admin_rating_badge(self):
        """Verify ChatMessageAdmin displays proper rating badge."""
        admin = ChatMessageAdmin(ChatMessage, AdminSite())
        
        up_msg = ChatMessage(sender="bot", message="Good answer", rating="thumbs_up")
        down_msg = ChatMessage(sender="bot", message="Bad answer", rating="thumbs_down", feedback_text="Wrong price")
        none_msg = ChatMessage(sender="bot", message="Regular", rating=None)

        self.assertIn("👍 Helpful", admin.rating_badge(up_msg))
        self.assertIn("👎 Poor", admin.rating_badge(down_msg))
        self.assertIn("Wrong price", admin.rating_badge(down_msg))
        self.assertEqual("—", admin.rating_badge(none_msg))

    def test_query_condensation_empty_history(self):
        """Empty history returns original query unchanged."""
        query = "Show me gaming laptops"
        result = condense_query_with_history(query, history=[])
        self.assertEqual(result, query)

    def test_query_condensation_heuristic_context(self):
        """Follow-up with short message combines context from previous turns if LLM unavailable."""
        history = [
            {"role": "user", "content": "Show me Sony headphones"},
            {"role": "assistant", "content": "Here are Sony headphones..."},
        ]
        with patch("openai.OpenAI", side_effect=Exception("Ollama offline")):
            condensed = condense_query_with_history("under 5000", history=history)
            # Should detect brand Sony or headphones category from history
            self.assertTrue("Sony" in condensed or "under 5000" in condensed)

    def test_query_condensation_llm_rewrite(self):
        """When LLM is available, condense_query_with_history returns rewritten query."""
        history = [
            {"role": "user", "content": "I am looking for gaming laptops"},
            {"role": "assistant", "content": "We have several Asus and Dell models."},
        ]
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "gaming laptops under 60000"
        mock_resp.choices = [mock_choice]
        mock_client.return_value.chat.completions.create.return_value = mock_resp

        with patch("openai.OpenAI", mock_client):
            condensed = condense_query_with_history("what about under 60k?", history=history)
            self.assertEqual(condensed, "gaming laptops under 60000")

    @patch("openai.OpenAI")
    def test_generate_chat_response_few_shot_prompt(self, mock_openai):
        """Verify generate_chat_response prompt includes few-shot examples."""
        mock_client_instance = MagicMock()
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Here are our recommendations."
        mock_resp.choices = [mock_choice]
        mock_client_instance.chat.completions.create.return_value = mock_resp
        mock_openai.return_value = mock_client_instance

        with patch("chatbot.rag_service.retrieve_relevant_products", return_value=[]):
            res = generate_chat_response("Do you have iPads?")
            self.assertEqual(res["reply"], "Here are our recommendations.")

            # Check that prompt contains FEW-SHOT EXAMPLES
            calls = mock_client_instance.chat.completions.create.call_args_list
            self.assertTrue(len(calls) > 0)
            system_msg = next(m["content"] for m in calls[0].kwargs["messages"] if m["role"] == "system")
            self.assertIn("FEW-SHOT EXAMPLES", system_msg)
            self.assertIn("Apple iPad 9th Gen", system_msg)

    def test_feedback_api_success_and_clear(self):
        """POST /chatbot/api/feedback/ updates rating and supports clearing."""
        msg = ChatMessage.objects.create(
            sender="bot",
            message="Here is a laptop recommendation.",
            session_key="test-session-123"
        )

        url = reverse("chatbot:api_feedback")

        # 1. Rate thumbs up
        res = self.client.post(
            url,
            data=json.dumps({"message_id": msg.id, "rating": "thumbs_up", "feedback": "Great advice"}),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["rating"], "thumbs_up")

        msg.refresh_from_db()
        self.assertEqual(msg.rating, "thumbs_up")
        self.assertEqual(msg.feedback_text, "Great advice")

        # 2. Rate thumbs down
        res2 = self.client.post(
            url,
            data=json.dumps({"message_id": msg.id, "rating": "thumbs_down"}),
            content_type="application/json"
        )
        self.assertEqual(res2.status_code, 200)
        msg.refresh_from_db()
        self.assertEqual(msg.rating, "thumbs_down")

        # 3. Clear rating
        res3 = self.client.post(
            url,
            data=json.dumps({"message_id": msg.id, "rating": "clear"}),
            content_type="application/json"
        )
        self.assertEqual(res3.status_code, 200)
        msg.refresh_from_db()
        self.assertIsNone(msg.rating)

    def test_feedback_api_validation(self):
        """POST /chatbot/api/feedback/ handles missing or invalid inputs."""
        url = reverse("chatbot:api_feedback")

        # Missing message_id
        res = self.client.post(
            url,
            data=json.dumps({"rating": "thumbs_up"}),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 400)

        # Invalid rating string
        res2 = self.client.post(
            url,
            data=json.dumps({"message_id": 9999, "rating": "super_like"}),
            content_type="application/json"
        )
        self.assertEqual(res2.status_code, 400)

        # Nonexistent message
        res3 = self.client.post(
            url,
            data=json.dumps({"message_id": 999999, "rating": "thumbs_up"}),
            content_type="application/json"
        )
        self.assertEqual(res3.status_code, 404)

    @patch("chatbot.views.answer_user_query")
    def test_chat_api_returns_message_id(self, mock_answer):
        """POST /chatbot/api/chat/ returns message_id in response."""
        mock_answer.return_value = {
            "reply": "Here are top laptops.",
            "products": [],
            "model": "qwen2.5:7b"
        }

        url = reverse("chatbot:api_chat")
        res = self.client.post(
            url,
            data=json.dumps({"message": "Show laptops"}),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("message_id", data)
        self.assertIsInstance(data["message_id"], int)

    def test_semantic_product_search_live_database_rehydration(self):
        """ChromaDB results are rehydrated from live database records."""
        cat = Category.objects.create(name="Laptops", slug="laptops")
        brand = Brand.objects.create(name="Asus")
        prod = Product.objects.create(
            name="Asus ROG Zephyrus G14",
            slug="asus-rog-zephyrus-g14",
            category=cat,
            brand=brand,
            price=120000.00,
            stock=8,
            is_active=True
        )

        mock_collection = MagicMock()
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            "metadatas": [[{
                "product_id": prod.id,
                "name": "Old Outdated Name",
                "price": 99999.00,
                "category": "Laptops",
                "brand": "Asus",
                "stock": 1,
            }]]
        }

        with patch("chatbot.rag_service.get_chroma_collection", return_value=mock_collection):
            results = semantic_product_search("gaming laptop")
            self.assertEqual(len(results), 1)
            # Live DB values should override ChromaDB stale cache
            self.assertEqual(results[0]["name"], "Asus ROG Zephyrus G14")
            self.assertEqual(results[0]["price"], 120000.00)
            self.assertEqual(results[0]["stock"], 8)

    def test_order_tracking_latest_order_logged_in_user(self):
        """Authenticated user asking for latest order gets visual progress stepper and items."""
        order = Order.objects.create(
            user=self.user,
            status=Order.STATUS_PAID,
            recipient_name="Chat Tester",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            total_amount=45000.00
        )
        cat = Category.objects.create(name="Smartphones", slug="smartphones")
        brand = Brand.objects.create(name="OnePlus")
        prod = Product.objects.create(
            name="OnePlus 12",
            slug="oneplus-12",
            category=cat,
            brand=brand,
            price=45000.00,
            stock=10,
            is_active=True
        )
        OrderItem.objects.create(
            order=order,
            product=prod,
            quantity=1,
            price_at_purchase=45000.00
        )

        res = check_order_tracking_intent("where is my latest order", user=self.user)
        self.assertIsNotNone(res)
        self.assertIn("Latest Order", res["reply"])
        self.assertIn("Payment Confirmed", res["reply"])
        self.assertIn("Preparing Dispatch", res["reply"])
        self.assertIn("OnePlus 12", res["reply"])
        self.assertIn("45,000.00", res["reply"])

    def test_order_tracking_specific_order_stepper(self):
        """Specific order tracking displays shipping progress stepper and delivery estimate."""
        order = Order.objects.create(
            user=self.user,
            status=Order.STATUS_SHIPPED,
            recipient_name="Chat Tester",
            city="Mumbai",
            total_amount=15000.00
        )
        res = check_order_tracking_intent(f"track order #{order.id}", user=self.user)
        self.assertIsNotNone(res)
        self.assertIn(f"Order #{order.id}", res["reply"])
        self.assertIn("🚚 In Transit", res["reply"])
        self.assertIn("2–4 business days", res["reply"])

    def test_guest_order_tracking_with_email_verification(self):
        """Unauthenticated guest can track order by providing registered email address."""
        guest_user = User.objects.create_user(
            email="guestbuyer@example.com",
            password="password123",
            name="Guest Buyer"
        )
        order = Order.objects.create(
            user=guest_user,
            status=Order.STATUS_DELIVERED,
            recipient_name="Guest Buyer",
            city="Delhi",
            total_amount=8999.00
        )
        cat = Category.objects.create(name="Audio", slug="audio-guest")
        prod = Product.objects.create(
            name="Sony WH-1000XM5",
            slug="sony-wh-1000xm5",
            category=cat,
            price=8999.00,
            stock=5,
            is_active=True
        )
        OrderItem.objects.create(
            order=order,
            product=prod,
            quantity=1,
            price_at_purchase=8999.00
        )

        # 1. Correct email match
        query = f"Track order #{order.id} email: guestbuyer@example.com"
        res = check_order_tracking_intent(query, user=None)
        self.assertIsNotNone(res)
        self.assertIn("Verified Guest Tracking", res["reply"])
        self.assertIn("📦 Delivered", res["reply"])
        self.assertIn("Sony WH-1000XM5", res["reply"])

        # 2. Wrong email mismatch - blocked securely
        query_bad = f"Track order #{order.id} email: hacker@example.com"
        res_bad = check_order_tracking_intent(query_bad, user=None)
        self.assertIsNotNone(res_bad)
        self.assertIn("Order Verification Failed", res_bad["reply"])
        self.assertNotIn("Sony WH-1000XM5", res_bad["reply"])

    def test_guest_order_tracking_prompt_for_email(self):
        """Guest querying order without email is prompted to verify their checkout email."""
        order = Order.objects.create(
            user=self.user,
            status=Order.STATUS_PENDING,
            total_amount=5000.00
        )
        res = check_order_tracking_intent(f"Where is order #{order.id}", user=None)
        self.assertIsNotNone(res)
        self.assertIn("Guest Order Tracking", res["reply"])
        self.assertIn(f"Track order #{order.id} email: yourname@example.com", res["reply"])

    def test_retrieve_historical_chat_knowledge_thumbs_up(self):
        """Historical chat retriever extracts past thumbs-up Q&A pairs for in-context learning."""
        session_key = "test_knowledge_session_123"
        ChatMessage.objects.create(
            session_key=session_key,
            sender="user",
            message="Can I expand RAM on Asus TUF laptop?"
        )
        ChatMessage.objects.create(
            session_key=session_key,
            sender="bot",
            message="Yes, the Asus TUF Gaming laptop has dual SO-DIMM DDR4 slots and supports expansion up to 32GB RAM.",
            rating="thumbs_up"
        )

        knowledge = retrieve_historical_chat_knowledge("Asus TUF RAM expansion", user=None)
        self.assertTrue(len(knowledge) > 0)
        self.assertEqual(knowledge[0]["source"], "verified_thumbs_up_chat")
        self.assertIn("expand RAM on Asus TUF", knowledge[0]["question"])
        self.assertIn("dual SO-DIMM DDR4 slots", knowledge[0]["answer"])

    @patch("openai.OpenAI")
    def test_retrieve_historical_chat_knowledge_in_system_prompt(self, mock_openai):
        """System prompt dynamically includes learned historical chat knowledge."""
        mock_client_instance = MagicMock()
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Here is the verified answer."
        mock_resp.choices = [mock_choice]
        mock_client_instance.chat.completions.create.return_value = mock_resp
        mock_openai.return_value = mock_client_instance

        session_key = "test_prompt_sess_456"
        ChatMessage.objects.create(
            session_key=session_key,
            sender="user",
            message="Does Dell XPS have Thunderbolt 4?"
        )
        ChatMessage.objects.create(
            session_key=session_key,
            sender="bot",
            message="Yes! Dell XPS 13 and 15 come with 2x Thunderbolt 4 ports supporting 40Gbps data and power delivery.",
            rating="thumbs_up"
        )

        with patch("chatbot.rag_service.retrieve_relevant_products", return_value=[]):
            res = generate_chat_response("Dell XPS Thunderbolt ports")
            self.assertEqual(res["reply"], "Here is the verified answer.")

            calls = mock_client_instance.chat.completions.create.call_args_list
            self.assertTrue(len(calls) > 0)
            system_msg = next(m["content"] for m in calls[0].kwargs["messages"] if m["role"] == "system")
            self.assertIn("LEARNED HISTORICAL CHAT KNOWLEDGE", system_msg)
            self.assertIn("Dell XPS", system_msg)
            self.assertIn("Thunderbolt 4", system_msg)

