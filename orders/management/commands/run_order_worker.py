import time
import signal
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone


class Command(BaseCommand):
    help = "Continuously runs expired pending orders cleanup in background loop to auto-recover stock"

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=300,
            help="Polling interval in seconds between cleanup sweeps (default: 300 / 5 mins)",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Execute cleanup once and terminate",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        run_once = options["once"]
        self.running = True

        def signal_handler(signum, frame):
            self.stdout.write(self.style.WARNING("\nReceived shutdown signal. Stopping order worker gracefully..."))
            self.running = False

        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except (ValueError, AttributeError):
            # Not in main thread or signal unavailable
            pass

        self.stdout.write(self.style.SUCCESS(
            f"[*] EasyTech Store Order Cleanup Worker started at {timezone.now().isoformat()} "
            f"(Sweep interval: {interval}s)"
        ))

        while self.running:
            try:
                call_command("cleanup_expired_orders")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"[!] Error executing cleanup sweep: {e}"))

            if run_once or not self.running:
                break

            for _ in range(interval):
                if not self.running:
                    break
                time.sleep(1)

        self.stdout.write(self.style.SUCCESS("[*] Order cleanup worker stopped cleanly."))
