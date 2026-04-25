from django.contrib import admin

from .models import Order, OrderItem, TelegramNotification


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer_name",
        "customer_email",
        "customer_phone",
        "status",
        "subtotal_snapshot",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("customer_name", "customer_email", "customer_phone")
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "variant",
        "quantity",
        "unit_price_snapshot",
        "line_total_snapshot",
    )
    search_fields = (
        "product_name_snapshot",
        "color_name_snapshot",
        "size_name_snapshot",
    )


@admin.register(TelegramNotification)
class TelegramNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "chat_id",
        "status",
        "attempts",
        "next_attempt_at",
        "sent_at",
    )
    search_fields = ("order__id", "chat_id")
    list_filter = ("status",)