from django.db import models

from orders.models import Order


class PaymentStatus(models.TextChoices):
    CREATED = "created", "Created"
    PENDING = "pending", "Pending"
    SUCCEEDED = "succeeded", "Succeeded"
    CANCELED = "canceled", "Canceled"
    FAILED = "failed", "Failed"


class PaymentProvider(models.TextChoices):
    YOOKASSA = "yookassa", "YooKassa"
    STRIPE = "stripe", "Stripe"


class Payment(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="payment",
    )

    provider = models.CharField(
        max_length=20,
        choices=PaymentProvider.choices,
        default=PaymentProvider.YOOKASSA,
    )

    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.CREATED,
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="RUB")

    provider_payment_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    confirmation_url = models.URLField(blank=True, null=True)

    raw_response = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)