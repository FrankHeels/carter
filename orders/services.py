from django.db import transaction

from typing import Any, Mapping, TypedDict

from cart.cart import Cart
from shop.models import ProductVariant
from .models import Order, OrderItem, OrderStatus


class CartRow(TypedDict):
    variant_id: int
    quantity: int


class GuestCheckoutData(TypedDict):
    customer_name: str
    customer_email: str
    customer_phone: str
    delivery_city: str
    delivery_street: str
    delivery_house: str
    delivery_apartment: str
    delivery_postal_code: str
    delivery_comment: str


class PreparedOrderItem(TypedDict):
    variant: ProductVariant
    quantity: int
    unit_price_snapshot: int
    line_total_snapshot: int
    product_name_snapshot: str
    color_name_snapshot: str
    size_name_snapshot: str


class CheckoutError(Exception):
    default_message = "Checkout error."

    def __init__(self, message):
        super().__init__(message or self.default_message)


class EmptyCartError(CheckoutError):
    default_message = "Cannot place an order with an empty cart."


class CartChangedError(CheckoutError):
    default_message = "The cart has changed since the last update."


def _parse_cart_rows(raw_items: list[CartRow]) -> list[CartRow]:
    cart_rows = []
    seen_variant_ids: set[int] = set()

    for item in raw_items:
        variant_id_raw = item.get("variant_id")
        quantity_raw = item.get("quantity")

        try:
            variant_id = int(variant_id_raw)
            quantity = int(quantity_raw)
        except (TypeError, ValueError) as exc:
            raise CartChangedError() from exc

        if variant_id < 1 or quantity < 1:
            raise CartChangedError()

        if variant_id in seen_variant_ids:
            raise CartChangedError()

        seen_variant_ids.add(variant_id)
        cart_rows.append(
            {
                "variant_id": variant_id,
                "quantity": quantity,
            }
        )

    return cart_rows


def _extract_order_data(cleaned_data: Mapping[str, Any]) -> GuestCheckoutData:
    return {
        "customer_name": cleaned_data["customer_name"],
        "customer_email": cleaned_data["customer_email"],
        "customer_phone": cleaned_data["customer_phone"],
        "delivery_city": cleaned_data["delivery_city"],
        "delivery_street": cleaned_data["delivery_street"],
        "delivery_house": cleaned_data["delivery_house"],
        "delivery_apartment": cleaned_data["delivery_apartment"],
        "delivery_postal_code": cleaned_data["delivery_postal_code"],
        "delivery_comment": cleaned_data["delivery_comment"],
    }


def place_order_from_cart(cart: Cart, cleaned_data: Mapping[str, Any]) -> Order:
    # Получаем актуальные данные по товарам в корзине
    raw_items = [
        item.copy() for item in cart.cart
    ]  # или dict(item) для копирования словаря

    # Проверяем, что корзина не пуста
    if not raw_items:
        raise EmptyCartError()

    cart_rows = _parse_cart_rows(raw_items)
    order_data = _extract_order_data(cleaned_data)

    with transaction.atomic():
        variant_ids = [row["variant_id"] for row in cart_rows]

        live_variants = (
            ProductVariant.objects.select_for_update()
            .select_related("product", "size", "color")
            .filter(id__in=variant_ids)
        )
        variants_by_id = {variant.id: variant for variant in live_variants}

        if len(variants_by_id) != len(variant_ids):
            raise CartChangedError()

        prepared_items: list[PreparedOrderItem] = []
        subtotal_snapshot = 0

        # Проходим по строкам корзины, проверяем наличие товаров и готовим данные для создания заказа.
        for row in cart_rows:
            variant = variants_by_id.get(row["variant_id"])

            if variant is None:
                raise CartChangedError()

            quantity = row["quantity"]
            if quantity > variant.stock:
                raise CartChangedError()
            unit_price_snapshot = variant.product.price
            line_total_snapshot = unit_price_snapshot * quantity
            subtotal_snapshot += line_total_snapshot

            prepared_items.append(
                {
                    "variant": variant,
                    "quantity": quantity,
                    "unit_price_snapshot": unit_price_snapshot,
                    "line_total_snapshot": line_total_snapshot,
                    "product_name_snapshot": variant.product.name,
                    "color_name_snapshot": variant.color.name,
                    "size_name_snapshot": variant.size.name,
                }
            )

        order = Order.objects.create(
            status=OrderStatus.PLACED,
            subtotal_snapshot=subtotal_snapshot,
            **order_data,
        )

        for item in prepared_items:
            OrderItem.objects.create(
                order=order,
                variant=item["variant"],
                quantity=item["quantity"],
                unit_price_snapshot=item["unit_price_snapshot"],
                line_total_snapshot=item["line_total_snapshot"],
                product_name_snapshot=item["product_name_snapshot"],
                color_name_snapshot=item["color_name_snapshot"],
                size_name_snapshot=item["size_name_snapshot"],
            )

        for item in prepared_items:
            variant = item["variant"]
            variant.stock -= item["quantity"]
            variant.save()

        transaction.on_commit(cart.clear)
    return order
