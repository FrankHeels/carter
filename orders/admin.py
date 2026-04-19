from django.contrib import admin

from .models import Order, OrderItem


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

