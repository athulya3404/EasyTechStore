"""
Django Signals for EasyTech AI Chatbot.
Automatically synchronizes Product catalog changes into the persistent ChromaDB vector store in real time.
"""

import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from products.models import Product
from .rag_service import upsert_single_product, delete_single_product

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Product)
def product_post_save_sync_vector_store(sender, instance, created, **kwargs):
    """
    Real-time sync: When a product is created, updated, marked out of stock,
    or deactivated, immediately update its vector representation in ChromaDB.
    """
    try:
        upsert_single_product(instance)
    except Exception as exc:
        logger.warning(
            "Failed real-time ChromaDB sync on post_save for product %s: %s",
            instance.pk,
            exc,
        )


@receiver(post_delete, sender=Product)
def product_post_delete_sync_vector_store(sender, instance, **kwargs):
    """
    Real-time sync: When a product is deleted from the catalog, immediately
    remove its embedding from the ChromaDB collection.
    """
    try:
        delete_single_product(instance.pk)
    except Exception as exc:
        logger.warning(
            "Failed real-time ChromaDB delete on post_delete for product %s: %s",
            instance.pk,
            exc,
        )
