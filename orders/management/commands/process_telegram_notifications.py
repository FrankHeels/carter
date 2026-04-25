from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from datetime import timedelta

from orders.models import TelegramNotification, TelegramNotificationStatus
from orders.telegram_gateway import build_order_message, send_order_notification


class Command(BaseCommand):
    help = "Обрабатывает очередь уведомлений в Telegram о новых заказах"

    def _process_notification(
        self, notification: TelegramNotification, retry_minutes: int
    ) -> None:
        try:
            order = notification.order
            text = build_order_message(order)
            chat_id = notification.chat_id
            send_order_notification(chat_id, text)
        except Exception as exc:
            notification.status = TelegramNotificationStatus.FAILED
            notification.attempts += 1
            notification.last_error = str(exc)
            notification.next_attempt_at = timezone.now() + timedelta(
                minutes=retry_minutes
            )
            notification.updated_at = timezone.now()
            notification.save(
                update_fields=[
                    "status",
                    "attempts",
                    "last_error",
                    "next_attempt_at",
                    "updated_at",
                ]
            )
            return

        notification.status = TelegramNotificationStatus.SENT
        notification.sent_at = timezone.now()
        notification.last_error = ""
        notification.save(update_fields=["status", "sent_at", "updated_at"])

    def handle(self, *args, **options):
        now = timezone.now()
        retry_minutes = getattr(settings, "TELEGRAM_NOTIFICATION_RETRY_MINUTES", 10)

        with transaction.atomic():
            notifications = list(
                TelegramNotification.objects.select_for_update(skip_locked=True)
                .select_related("order")
                .prefetch_related("order__items")
                .filter(
                    status__in=[
                        TelegramNotificationStatus.PENDING,
                        TelegramNotificationStatus.FAILED,
                    ],
                    next_attempt_at__lte=now,
                )
                .order_by("next_attempt_at", "id")
            )
            for notification in notifications:
                self._process_notification(notification, retry_minutes)
        self.stdout.write(f"Processed {len(notifications)} Telegram notifications.")
