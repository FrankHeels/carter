from django.db import models


class OrderStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PLACED = "placed", "Placed"
    CANCELLED = "cancelled", "Cancelled"


class Order(models.Model):
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.DRAFT,
    )
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=50)

    delivery_city = models.CharField(max_length=255)
    delivery_street = models.CharField(max_length=255)
    delivery_house = models.CharField(max_length=50)
    delivery_apartment = models.CharField(max_length=50, blank=True)
    delivery_postal_code = models.CharField(max_length=20)
    delivery_comment = models.TextField(blank=True)

    subtotal_snapshot = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Order #{self.pk} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    variant = models.ForeignKey(
        "shop.ProductVariant",
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    quantity = models.PositiveIntegerField()

    unit_price_snapshot = models.PositiveIntegerField()
    line_total_snapshot = models.PositiveIntegerField()

    product_name_snapshot = models.CharField(max_length=255)
    color_name_snapshot = models.CharField(max_length=100)
    size_name_snapshot = models.CharField(max_length=50)

    def __str__(self) -> str:
        return f"OrderItem #{self.pk} for order #{self.order_id}"
