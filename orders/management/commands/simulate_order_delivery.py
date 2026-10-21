import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from orders.services_lifecycle import run_order_progression_sweep


class Command(BaseCommand):
    help = "Automated courier progression: Paid (after 1 hour) -> Shipped -> Delivered (after random product delivery days)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--immediate",
            action="store_true",
            help="Advance all eligible Paid and Shipped orders immediately without waiting (demo/test mode)",
        )
        parser.add_argument(
            "--delay-hours",
            type=int,
            default=1,
            help="Hours after payment before auto-shipping (default: 1 hour)",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Polling interval in seconds when running as continuous daemon (default: 60s)",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Execute a single sweep and terminate (ideal for cron)",
        )

    def handle(self, *args, **options):
        immediate = options["immediate"]
        delay_hours = options["delay_hours"]
        interval = options["interval"]
        run_once = options["once"]

        mode_str = "Immediate Demo" if immediate else f"Realistic (Delay: {delay_hours}h)"
        self.stdout.write(self.style.SUCCESS(
            f"[*] EasyTech Store Order Delivery Simulator active at {timezone.now().strftime('%Y-%m-%d %H:%M:%S')} "
            f"(Mode: {mode_str})"
        ))

        while True:
            res = run_order_progression_sweep(hours_delay=delay_hours, immediate=immediate)
            shipped = res["shipped_count"]
            delivered = res["delivered_count"]

            if shipped > 0 or delivered > 0:
                self.stdout.write(self.style.SUCCESS(
                    f"  -> Sweep result: {shipped} order(s) marked Shipped, {delivered} order(s) marked Delivered."
                ))
            else:
                self.stdout.write("  -> No orders currently due for status advancement.")

            if run_once or immediate:
                break

            time.sleep(interval)

