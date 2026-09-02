from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.utils import timezone

from erp.models import OutboundEmail


class Command(BaseCommand):
    help = "Retry pending and failed ERP emails."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        deliveries = OutboundEmail.objects.filter(
            status__in=["pending", "failed"],
            attempts__lt=5,
        ).order_by("created_at")[: options["limit"]]
        sent_count = 0
        for delivery in deliveries:
            message = EmailMultiAlternatives(
                delivery.subject,
                delivery.text_body,
                settings.DEFAULT_FROM_EMAIL,
                [delivery.recipient],
            )
            message.attach_alternative(delivery.html_body, "text/html")
            try:
                sent = message.send()
                delivery.status = "sent" if sent else "failed"
                delivery.sent_at = timezone.now() if sent else None
                delivery.last_error = (
                    "" if sent else "Email backend returned zero deliveries."
                )
                sent_count += int(bool(sent))
            except Exception as exc:
                delivery.status = "failed"
                delivery.last_error = str(exc)[:2000]
            delivery.attempts += 1
            delivery.save(
                update_fields=[
                    "status",
                    "sent_at",
                    "last_error",
                    "attempts",
                    "updated_at",
                ]
            )
        self.stdout.write(self.style.SUCCESS(f"Sent {sent_count} email(s)."))
