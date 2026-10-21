"""
Django Signals for Product Model.
Automatically keeps the ChromaDB vector database in sync when products are
created, updated, or deleted via Django Admin, Manager Dashboard, or bulk CSV imports.
"""

import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Product

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Product)
def sync_product_to_chromadb(sender, instance, created, **kwargs):
    """
    Automatically upserts or updates product vector embeddings in ChromaDB
    whenever a product is saved or toggled active/inactive.
    """
    try:
        from chatbot.rag_service import upsert_single_product
        upsert_single_product(instance)
    except Exception as exc:
        logger.debug("ChromaDB background sync skipped on post_save: %s", exc)


@receiver(post_delete, sender=Product)
def remove_product_from_chromadb(sender, instance, **kwargs):
    """
    Automatically removes product vector embeddings from ChromaDB
    when a product is deleted from the store.
    """
    try:
        from chatbot.rag_service import delete_single_product
        delete_single_product(instance.id)
    except Exception as exc:
        logger.debug("ChromaDB background sync skipped on post_delete: %s", exc)
