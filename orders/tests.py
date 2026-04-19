from __future__ import annotations

from types import SimpleNamespace

from django.apps import apps
from django.contrib import admin
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from orders.models import Order, OrderItem, OrderStatus
from shop.models import Category, Color, Product, ProductVariant, Size


def create_catalog_fixture(
    *,
    suffix: str,
    price: int = 100,
    size_name: str = "M",
    size_order: int = 1,
    color_name: str = "Black",
    hex_code: str = "#111111",
    stock: int = 10,
) -> SimpleNamespace:
    category = Category.objects.create(
        name=f"Category {suffix}",
        slug=f"category-{suffix}",
    )
    product = Product.objects.create(
        name=f"Product {suffix}",
        description="Test product description.",
        care_instructions="Test care instructions.",
        price=price,
        category=category,
        slug=f"product-{suffix}",
    )
    color = Color.objects.create(
        name=color_name,
        hex_code=hex_code,
    )
    size = Size.objects.create(
        name=size_name,
        order=size_order,
    )
    variant = ProductVariant.objects.create(
        product=product,
        color=color,
        size=size,
        stock=stock,
    )
    return SimpleNamespace(
        category=category,
        product=product,
        color=color,
        size=size,
        variant=variant,
    )


class OrderSnapshotTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.catalog = create_catalog_fixture(
            suffix="primary",
            price=150,
            size_name="M",
            size_order=1,
            color_name="Black",
            hex_code="#111111",
            stock=10,
        )

    def create_order_with_item(
        self,
        *,
        quantity: int = 2,
        unit_price_snapshot: int | None = None,
        line_total_snapshot: int | None = None,
        subtotal_snapshot: int | None = None,
    ) -> tuple[Order, OrderItem]:
        unit_price = unit_price_snapshot or self.catalog.product.price
        line_total = line_total_snapshot or unit_price * quantity
        subtotal = subtotal_snapshot or line_total

        order = Order.objects.create(
            status=OrderStatus.PLACED,
            customer_name="Ivan Ivanov",
            customer_email="ivan@example.com",
            customer_phone="+79990000000",
            delivery_city="Moscow",
            delivery_street="Tverskaya",
            delivery_house="10",
            delivery_apartment="15",
            delivery_postal_code="123456",
            delivery_comment="Call before delivery",
            subtotal_snapshot=subtotal,
        )
        item = OrderItem.objects.create(
            order=order,
            variant=self.catalog.variant,
            quantity=quantity,
            unit_price_snapshot=unit_price,
            line_total_snapshot=line_total,
            product_name_snapshot=self.catalog.product.name,
            color_name_snapshot=self.catalog.color.name,
            size_name_snapshot=self.catalog.size.name,
        )
        return order, item

    def test_order_item_keeps_price_snapshots_after_catalog_price_changes(self):
        """Snapshot prices must stay historical after the catalog price changes."""
        order, item = self.create_order_with_item(
            quantity=3,
            unit_price_snapshot=150,
            line_total_snapshot=450,
            subtotal_snapshot=450,
        )

        self.catalog.product.price = 999
        self.catalog.product.save(update_fields=["price"])

        item.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(self.catalog.product.price, 999)
        self.assertEqual(item.unit_price_snapshot, 150)
        self.assertEqual(item.line_total_snapshot, 450)
        self.assertEqual(order.subtotal_snapshot, 450)

    def test_order_item_keeps_name_snapshots_after_catalog_name_changes(self):
        """Snapshot names must not follow later renames in product, color, or size."""
        _, item = self.create_order_with_item()

        self.catalog.product.name = "Renamed Product"
        self.catalog.product.save(update_fields=["name"])

        self.catalog.color.name = "White"
        self.catalog.color.save(update_fields=["name"])

        self.catalog.size.name = "XL"
        self.catalog.size.save(update_fields=["name"])

        item.refresh_from_db()

        self.assertEqual(item.product_name_snapshot, "Product primary")
        self.assertEqual(item.color_name_snapshot, "Black")
        self.assertEqual(item.size_name_snapshot, "M")

    def test_order_keeps_subtotal_snapshot_after_catalog_price_changes(self):
        """Order subtotal must remain frozen even if the product price changes later."""
        order, item = self.create_order_with_item(
            quantity=2,
            unit_price_snapshot=150,
            line_total_snapshot=300,
            subtotal_snapshot=300,
        )

        self.catalog.product.price = 50
        self.catalog.product.save(update_fields=["price"])

        order.refresh_from_db()
        item.refresh_from_db()

        self.assertEqual(self.catalog.product.price, 50)
        self.assertEqual(item.unit_price_snapshot, 150)
        self.assertEqual(item.line_total_snapshot, 300)
        self.assertEqual(order.subtotal_snapshot, 300)

    def test_order_item_variant_is_protected_from_deletion(self):
        """Historical order items must block deletion of the referenced variant."""
        self.create_order_with_item()

        with self.assertRaises(ProtectedError):
            self.catalog.variant.delete()


class OrdersConfigurationTests(TestCase):
    def test_orders_app_is_installed(self):
        """The orders domain must be connected to Django settings."""
        self.assertTrue(apps.is_installed("orders"))

    def test_order_and_order_item_are_registered_in_admin(self):
        """Both order models must be available in Django admin for debugging."""
        self.assertIn(Order, admin.site._registry)
        self.assertIn(OrderItem, admin.site._registry)

    def test_checkout_route_redirects_to_cart_when_cart_is_empty(self):
        """Checkout must stay public, but an empty cart must bounce back to cart."""
        response = self.client.get(reverse("orders:checkout"))

        self.assertRedirects(response, reverse("cart_detail"))


class OrderCheckoutViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.catalog = create_catalog_fixture(suffix="success-view")
        cls.order = Order.objects.create(
            status=OrderStatus.PLACED,
            customer_name="Ivan Ivanov",
            customer_email="ivan@example.com",
            customer_phone="+79990000000",
            delivery_city="Moscow",
            delivery_street="Tverskaya",
            delivery_house="10",
            delivery_apartment="15",
            delivery_postal_code="123456",
            delivery_comment="Call before delivery",
            subtotal_snapshot=100,
        )

    def test_success_redirects_to_cart_without_last_order_id(self):
        """Direct access to success without a fresh checkout must return to cart."""
        response = self.client.get(reverse("orders:success"))

        self.assertRedirects(response, reverse("cart_detail"))

    def test_success_renders_confirmation_for_last_order_id_in_session(self):
        """Success page must render confirmation for the order stored in session."""
        session = self.client.session
        session["last_order_id"] = self.order.id
        session.save()

        response = self.client.get(reverse("orders:success"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["order"], self.order)

    def test_success_consumes_last_order_id_after_confirmation(self):
        """Confirmation token in session should be single-use."""
        session = self.client.session
        session["last_order_id"] = self.order.id
        session.save()

        self.client.get(reverse("orders:success"))

        session = self.client.session
        self.assertNotIn("last_order_id", session)

    def test_checkout_renders_form_and_summary_for_non_empty_cart(self):
        """Checkout should render the guest form and cart summary when cart has items."""
        session = self.client.session
        session["cart"] = [
            {
                "variant_id": str(self.catalog.variant.id),
                "quantity": 2,
            }
        ]
        session.save()
        self.client.raise_request_exception = False

        response = self.client.get(reverse("orders:checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Оформление заказа")
        self.assertContains(response, self.catalog.product.name)
        self.assertContains(response, "Итого")
        self.assertContains(response, "customer_name")

    def test_checkout_invalid_post_returns_errors_without_clearing_cart(self):
        """Invalid checkout submission should keep cart state and show field errors."""
        session = self.client.session
        session["cart"] = [
            {
                "variant_id": str(self.catalog.variant.id),
                "quantity": 1,
            }
        ]
        session.save()
        self.client.raise_request_exception = False

        response = self.client.post(
            reverse("orders:checkout"),
            data={},
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Заполните это поле", status_code=400)
        self.assertEqual(self.client.session["cart"][0]["variant_id"], str(self.catalog.variant.id))

    def test_success_shows_receipt_data_from_order_snapshots(self):
        """Success page should show order number, subtotal, and snapshot item details."""
        OrderItem.objects.create(
            order=self.order,
            variant=self.catalog.variant,
            quantity=2,
            unit_price_snapshot=50,
            line_total_snapshot=100,
            product_name_snapshot="Snapshot Hoodie",
            color_name_snapshot="Black",
            size_name_snapshot="M",
        )
        session = self.client.session
        session["last_order_id"] = self.order.id
        session.save()
        self.client.raise_request_exception = False

        response = self.client.get(reverse("orders:success"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"#{self.order.id}")
        self.assertContains(response, "Snapshot Hoodie")
        self.assertContains(response, "100")
        self.assertContains(response, "Заказ оформлен")

    def test_cart_page_contains_checkout_link_for_non_empty_cart(self):
        """Cart page should expose a checkout CTA when there are items in cart."""
        session = self.client.session
        session["cart"] = [
            {
                "variant_id": str(self.catalog.variant.id),
                "quantity": 1,
            }
        ]
        session.save()

        response = self.client.get(reverse("cart_detail"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("orders:checkout"))


class OrderCheckoutTransactionTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.catalog = create_catalog_fixture(suffix="checkout-post")

    def test_checkout_valid_post_creates_order_and_redirects_to_success(self):
        """Successful checkout should persist snapshots, clear cart, and redirect to success."""
        session = self.client.session
        session["cart"] = [
            {
                "variant_id": str(self.catalog.variant.id),
                "quantity": 2,
            }
        ]
        session.save()

        response = self.client.post(
            reverse("orders:checkout"),
            data={
                "customer_name": "Иван Иванов",
                "customer_email": "ivan@example.com",
                "customer_phone": "+79990000000",
                "delivery_city": "Москва",
                "delivery_street": "Тверская",
                "delivery_house": "10",
                "delivery_apartment": "15",
                "delivery_postal_code": "123456",
                "delivery_comment": "Позвоните за час",
            },
        )

        order = Order.objects.get()
        order_item = order.items.get()
        self.catalog.variant.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("orders:success"))
        self.assertEqual(order.status, OrderStatus.PLACED)
        self.assertEqual(order.subtotal_snapshot, 200)
        self.assertEqual(order_item.product_name_snapshot, self.catalog.product.name)
        self.assertEqual(order_item.color_name_snapshot, self.catalog.color.name)
        self.assertEqual(order_item.size_name_snapshot, self.catalog.size.name)
        self.assertEqual(order_item.quantity, 2)
        self.assertEqual(order_item.line_total_snapshot, 200)
        self.assertEqual(self.catalog.variant.stock, 8)
        self.assertEqual(self.client.session["cart"], [])
        self.assertEqual(self.client.session["last_order_id"], order.id)
