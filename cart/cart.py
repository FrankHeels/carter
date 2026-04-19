from collections.abc import Iterator

from shop.models import ProductVariant


class Cart:
    CART_SESSION_KEY = "cart"

    def __init__(self, request) -> None:
        self.session = request.session
        cart = self.session.get(self.CART_SESSION_KEY)

        if cart is None:
            cart = self.session[self.CART_SESSION_KEY] = []

        self.cart: list[dict[str, int | str]] = cart
        self._runtime_items: list[dict[str, object]] | None = None

    def _can_keep_variant(self, variant: ProductVariant) -> bool:
        return variant.is_available

    def _normalize_quantity(self, variant: ProductVariant, quantity: int) -> int:
        if not self._can_keep_variant(variant):
            return 0

        try:
            normalized_quantity = int(quantity)
        except (TypeError, ValueError):
            return 0

        return min(max(1, normalized_quantity), variant.stock)

    def _build_runtime_items(self) -> list[dict[str, object]]:
        """
        Строит список товаров в корзине с полной информацией о варианте и общей ценой.
            - Удаляет из корзины несуществующие варианты.
            - Нормализует количество (не меньше 1 и не больше наличия на складе).
        """
        if self._runtime_items is not None:
            return self._runtime_items

        variant_ids = [str(item.get("variant_id", "")) for item in self.cart]
        variants = ProductVariant.objects.filter(id__in=variant_ids).select_related(
            "product", "size", "color"
        )
        variants_map = {str(variant.id): variant for variant in variants}

        cleaned_cart: list[dict[str, int | str]] = []
        runtime_items: list[dict[str, object]] = []

        # Проходим по элементам в сессии, проверяем их валидность и строим список для отображения.
        for session_item in self.cart:
            variant_id = str(session_item.get("variant_id", ""))

            try:
                quantity = int(session_item.get("quantity", 0))
            except (TypeError, ValueError):
                continue

            if quantity < 1:
                continue

            variant = variants_map.get(variant_id)
            if variant is None:
                continue

            quantity = self._normalize_quantity(variant, quantity)
            if quantity == 0:
                continue

            cleaned_item = {
                "variant_id": variant_id,
                "quantity": quantity,
            }
            cleaned_cart.append(cleaned_item)

            runtime_items.append(
                {
                    "variant_id": variant_id,
                    "quantity": quantity,
                    "variant": variant,
                    "total_price": variant.product.price * quantity,
                }
            )

        if cleaned_cart != self.cart:
            self.cart = cleaned_cart
            self.session[self.CART_SESSION_KEY] = cleaned_cart
            self.save()

        self._runtime_items = runtime_items
        return runtime_items

    def _find_item(self, variant: ProductVariant) -> dict[str, int | str] | None:
        variant_id = str(variant.id)

        for item in self.cart:
            if item["variant_id"] == variant_id:
                return item
        return None

    def get_quantity(self, variant: ProductVariant) -> int:
        variant_id = str(variant.id)

        for item in self._build_runtime_items():
            if item["variant_id"] == variant_id:
                return int(item["quantity"])

        return 0

    def _set_quantity(self, variant: ProductVariant, quantity: int) -> None:
        item = self._find_item(variant)
        normalized_quantity = self._normalize_quantity(variant, quantity)

        if normalized_quantity == 0:
            if item is not None:
                self.cart = [
                    cart_item
                    for cart_item in self.cart
                    if cart_item["variant_id"] != str(variant.id)
                ]
                self.session[self.CART_SESSION_KEY] = self.cart
                self.save()
            return

        if item is not None:
            item["quantity"] = normalized_quantity
        else:
            self.cart.append(
                {
                    "variant_id": str(variant.id),
                    "quantity": normalized_quantity,
                }
            )

        self.session[self.CART_SESSION_KEY] = self.cart
        self.save()

    def add(self, variant: ProductVariant, quantity: int = 1) -> None:
        current_quantity = self.get_quantity(variant)
        self._set_quantity(variant, current_quantity + max(1, int(quantity)))

    def increment(self, variant: ProductVariant) -> None:
        current_quantity = self.get_quantity(variant)

        if current_quantity < 1:
            return

        self._set_quantity(variant, current_quantity + 1)

    def decrement(self, variant: ProductVariant) -> None:
        current_quantity = self.get_quantity(variant)

        if current_quantity < 1:
            return

        self._set_quantity(variant, current_quantity - 1)

    # def update(self, variant: ProductVariant, quantity: int) -> None:
    #     variant_id = str(variant.id)
    #     quantity = max(1, int(quantity))

    #     for item in self.cart:
    #         if item["variant_id"] == variant_id:
    #             item["quantity"] = quantity
    #             self.session[self.CART_SESSION_KEY] = self.cart
    #             self.save()
    #             return

    def remove(self, variant: ProductVariant) -> None:
        variant_id = str(variant.id)
        self.cart = [item for item in self.cart if item["variant_id"] != variant_id]
        self.session[self.CART_SESSION_KEY] = self.cart
        self.save()

    def clear(self) -> None:
        self.cart = []
        self.session[self.CART_SESSION_KEY] = []
        self.save()

    def get_total_price(self) -> int:
        return sum(item["total_price"] for item in self._build_runtime_items())

    def __len__(self) -> int:
        return sum(int(item["quantity"]) for item in self._build_runtime_items())

    def __iter__(self) -> Iterator[dict[str, object]]:
        yield from self._build_runtime_items()

    def save(self) -> None:
        self._runtime_items = None
        self.session.modified = True
