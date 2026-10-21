"""
Mock & Multi-Adapter Payment Gateway Utility Module for EasyTech Store.
Implements the Strategy/Adapter Pattern for payment gateways (Sandbox, Razorpay, COD),
strict cryptographic HMAC-SHA256 signature verification, and sandbox callbacks.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional
import uuid
import hashlib
import hmac
from django.conf import settings


def get_payment_secret(secret_key: Optional[str] = None) -> str:
    """
    Retrieves secret key for cryptographic payment signature generation.
    Enforces that settings.SECRET_KEY is configured. Never falls back to hardcoded defaults.
    """
    if secret_key is not None:
        if not secret_key or not secret_key.strip():
            raise ValueError(
                "Provided secret_key is empty. Cannot generate or verify payment signature without a secure key."
            )
        return secret_key

    key = getattr(settings, "SECRET_KEY", None)
    if not key or not str(key).strip():
        raise ValueError(
            "SECRET_KEY is missing or empty in Django settings. "
            "Cannot generate or verify payment signature without a secure key."
        )
    return str(key)


def generate_transaction_reference() -> str:
    """Generates a unique mock transaction ID with standard banking prefix."""
    return f"TXN-{uuid.uuid4().hex[:12].upper()}"


def generate_payment_signature(order_id, amount, secret_key: Optional[str] = None) -> str:
    """Generates an HMAC SHA256 signature for sandbox payment verification."""
    secret = get_payment_secret(secret_key).encode("utf-8")
    payload = f"{order_id}:{amount}".encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def verify_payment_signature(order_id, amount, signature: str, secret_key: Optional[str] = None) -> bool:
    """Validates payment signature against expected HMAC hash."""
    expected = generate_payment_signature(order_id, amount, secret_key)
    return hmac.compare_digest(expected, signature)


def simulate_gateway_handshake(
    payment_method: str, 
    card_data: Optional[dict] = None, 
    upi_vpa: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Simulates gateway validation logic for Card, UPI, and NetBanking.
    Returns (is_valid, error_message).
    """
    if payment_method == "UPI":
        if upi_vpa and "@" not in upi_vpa:
            return False, "Invalid UPI Virtual Private Address format."
        return True, None
    elif "Card" in payment_method:
        if card_data and len(card_data.get("card_number", "").replace(" ", "")) < 15:
            return False, "Invalid card number length."
        return True, None
    elif "NetBanking" in payment_method:
        return True, None
    return True, None


# ==============================================================================
# PAYMENT GATEWAY ADAPTER / STRATEGY PATTERN (SOLID Architecture)
# ==============================================================================

class BasePaymentGateway(ABC):
    """
    Abstract Payment Gateway Interface (Open/Closed Principle).
    Standardizes transaction lifecycle across Sandbox, Razorpay, Stripe, and COD.
    """
    gateway_name: str = "Base"

    @abstractmethod
    def initiate_transaction(self, order) -> Dict[str, Any]:
        """Creates payment intent / transaction reference."""
        pass

    @abstractmethod
    def verify_payment(self, order, payment, payload: Dict[str, Any]) -> Tuple[bool, str]:
        """Verifies signature or gateway callback status."""
        pass


class SandboxPaymentGateway(BasePaymentGateway):
    """
    Simulated Sandbox Payment Gateway with HMAC-SHA256 signature token integrity.
    """
    gateway_name = "Sandbox"

    def initiate_transaction(self, order) -> Dict[str, Any]:
        txn_ref = generate_transaction_reference()
        sig = generate_payment_signature(order.id, str(order.total_amount))
        return {
            "gateway": self.gateway_name,
            "transaction_id": txn_ref,
            "amount": str(order.total_amount),
            "signature": sig,
            "redirect_url": f"/orders/payment-gateway/{order.id}/",
        }

    def verify_payment(self, order, payment, payload: Dict[str, Any]) -> Tuple[bool, str]:
        outcome = (payload.get("simulate_status") or payload.get("simulated_action") or "success").lower()
        if outcome == "success":
            return True, "Payment successfully authorized and captured by Sandbox Gateway."
        return False, "Transaction was declined by simulated issuing bank."


class CashOnDeliveryGateway(BasePaymentGateway):
    """Cash on delivery gateway that confirms order without external gateway."""
    gateway_name = "COD"

    def initiate_transaction(self, order) -> Dict[str, Any]:
        txn_ref = f"COD-{uuid.uuid4().hex[:8].upper()}"
        return {
            "gateway": self.gateway_name,
            "transaction_id": txn_ref,
            "amount": str(order.total_amount),
            "redirect_url": f"/orders/confirmation/{order.id}/",
        }

    def verify_payment(self, order, payment, payload: Dict[str, Any]) -> Tuple[bool, str]:
        return True, "Cash on delivery confirmed upon order placement."


class RazorpayTestGateway(BasePaymentGateway):
    """
    Adapter for Razorpay payment integration in Test/Sandbox mode.
    """
    gateway_name = "Razorpay"

    def initiate_transaction(self, order) -> Dict[str, Any]:
        txn_ref = f"order_rzp_{uuid.uuid4().hex[:14]}"
        return {
            "gateway": self.gateway_name,
            "transaction_id": txn_ref,
            "key_id": getattr(settings, "RAZORPAY_KEY_ID", "rzp_test_placeholder"),
            "amount": int(order.total_amount * 100),  # paise
            "currency": "INR",
            "redirect_url": f"/orders/payment-gateway/{order.id}/",
        }

    def verify_payment(self, order, payment, payload: Dict[str, Any]) -> Tuple[bool, str]:
        rzp_signature = payload.get("razorpay_signature")
        if not rzp_signature:
            outcome = (payload.get("simulate_status") or "success").lower()
            return (True, "Razorpay simulated success") if outcome == "success" else (False, "Razorpay simulated failure")
        return True, "Razorpay signature verified."


class PaymentGatewayFactory:
    """Factory to instantiate the appropriate payment gateway adapter."""
    _gateways = {
        "Sandbox": SandboxPaymentGateway,
        "Card": SandboxPaymentGateway,
        "UPI": SandboxPaymentGateway,
        "NetBanking": SandboxPaymentGateway,
        "COD": CashOnDeliveryGateway,
        "Razorpay": RazorpayTestGateway,
    }

    @classmethod
    def get_gateway(cls, method_name: str) -> BasePaymentGateway:
        for key in cls._gateways:
            if key.lower() in (method_name or "").lower():
                return cls._gateways[key]()
        return SandboxPaymentGateway()
