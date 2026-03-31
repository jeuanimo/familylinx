import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

TARGET_URL = "https://fam-linx.org/"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10


class Command(BaseCommand):
    help = "Ping fam-linx.org to keep the instance warm. Retries on failure and sends alert email if all retries fail."

    def handle(self, *args, **options):
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(
                    TARGET_URL,
                    headers={"User-Agent": "FamilyLinx-Keepalive/1.0"},
                )
                with urllib.request.urlopen(req, timeout=15) as response:
                    status = response.status
                self.stdout.write(
                    self.style.SUCCESS(f"[attempt {attempt}] ping ok — HTTP {status}")
                )
                return  # success — done
            except Exception as exc:
                last_error = exc
                self.stderr.write(
                    self.style.WARNING(
                        f"[attempt {attempt}/{MAX_RETRIES}] ping failed: {exc}"
                    )
                )
                if attempt < MAX_RETRIES:
                    self.stdout.write(f"Retrying in {RETRY_DELAY_SECONDS}s...")
                    time.sleep(RETRY_DELAY_SECONDS)

        # All retries exhausted — send alert email
        self.stderr.write(self.style.ERROR("All retries failed. Sending alert email."))
        try:
            alert_email = getattr(settings, "DEFAULT_FROM_EMAIL", "contact@fam-linx.org")
            send_mail(
                subject="🚨 FamilyLinx keepalive ping failed",
                message=(
                    f"All {MAX_RETRIES} keepalive ping attempts to {TARGET_URL} failed.\n\n"
                    f"Last error: {last_error}\n\n"
                    "Please check the Render dashboard to ensure the service is running."
                ),
                from_email=alert_email,
                recipient_list=[alert_email],
                fail_silently=True,
            )
            self.stdout.write("Alert email sent.")
        except Exception as mail_exc:
            self.stderr.write(f"Failed to send alert email: {mail_exc}")

        raise SystemExit(1)
