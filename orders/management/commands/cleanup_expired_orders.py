from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.db.models import F
from orders.models import Order
from products.models import Product


class Command(BaseCommand):
    help = (
        "Releases reserved inventory and permanently deletes abandoned checkout orders "
        "that have exceeded their 10-minute expiration window."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes",
            type=int,
            default=10,
            help="Fallback expiration duration in minutes if order has no explicit expires_at timestamp.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate cleanup without updating database records.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        fallback_minutes = options["minutes"]
        fallback_cutoff = now - timedelta(minutes=fallback_minutes)

        # Orders that either have an expires_at timestamp past due,
        # OR pending orders older than fallback_minutes if expires_at was null
        expired_orders = Order.objects.filter(
            status__in=[Order.STATUS_PENDING, Order.STATUS_PAYMENT_PENDING]
        ).filter(
            expires_at__lte=now
        ) | Order.objects.filter(
            status__in=[Order.STATUS_PENDING, Order.STATUS_PAYMENT_PENDING],
            expires_at__isnull=True,
            created_at__lte=fallback_cutoff,
        )

        expired_orders = expired_orders.distinct()
        total_deleted = 0
        total_items_restored = 0

        self.stdout.write(
            self.style.NOTICE(f"Scanning for expired pending orders (current time: {now})...")
        )

        dry_run = options.get("dry_run", False)
        for order in expired_orders:
            with transaction.atomic():
                # Re-fetch with row lock to avoid race conditions
                locked_order = (
                    Order.objects.select_for_update()
                    .filter(id=order.id, status__in=[Order.STATUS_PENDING, Order.STATUS_PAYMENT_PENDING])
                    .first()
                )
                if not locked_order:
                    continue

                items_restored_count = sum(
                    item.quantity for item in locked_order.items.all() if item.product_id
                )

                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[DRY RUN] Would delete Order #{locked_order.id} (user: {locked_order.user.email}) "
                            f"and restore {items_restored_count} product unit(s)."
                        )
                    )
                    total_deleted += 1
                    total_items_restored += items_restored_count
                    continue

                for item in locked_order.items.select_related("product").all():
                    if item.product_id:
                        Product.objects.filter(id=item.product_id).update(
                            stock=F("stock") + item.quantity
                        )

                order_id_val = locked_order.id
                user_email_val = locked_order.user.email if locked_order.user else "Customer"
                locked_order.delete()

                total_deleted += 1
                total_items_restored += items_restored_count

                self.stdout.write(
                    f"Deleted Order #{order_id_val} (user: {user_email_val}). "
                    f"Restored {items_restored_count} product unit(s)."
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully deleted {total_deleted} expired order(s) and "
                f"restored {total_items_restored} item(s) back to inventory stock."
            )
        )
