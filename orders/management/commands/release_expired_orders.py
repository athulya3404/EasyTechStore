from orders.management.commands.cleanup_expired_orders import Command as CleanupCommand


class Command(CleanupCommand):
    help = "Alias for cleanup_expired_orders."
