from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib import admin
from django.core.management import call_command
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from orders.models import (
    Order,
    OrderItem,
    OrderStatus,
    TelegramNotification,
    TelegramNotificationStatus,
)
from orders.telegram_gateway import build_order_message
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

    def test_order_models_are_registered_in_admin(self):
        """Order models must be available in Django admin for debugging."""
        self.assertIn(Order, admin.site._registry)
        self.assertIn(OrderItem, admin.site._registry)
        self.assertIn(TelegramNotification, admin.site._registry)

    def test_telegram_notification_admin_exposes_diagnostics(self):
        """Telegram notification admin should expose retry diagnostics."""
        telegram_admin = admin.site._registry[TelegramNotification]

        self.assertEqual(
            telegram_admin.list_display,
            (
                "order",
                "chat_id",
                "status",
                "attempts",
                "next_attempt_at",
                "sent_at",
            ),
        )
        self.assertEqual(telegram_admin.list_filter, ("status",))
        self.assertEqual(telegram_admin.search_fields, ("order__id", "chat_id"))

    def test_checkout_route_redirects_to_cart_when_cart_is_empty(self):
        """Checkout must stay public, but an empty cart must bounce back to cart."""
        response = self.client.get(reverse("orders:checkout"))

        self.assertRedirects(response, reverse("cart_detail"))


class TelegramGatewayMessageTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.catalog = create_catalog_fixture(suffix="telegram-message")

    def test_build_order_message_uses_order_and_item_snapshots(self):
        """Telegram message should use frozen order and item snapshot data."""
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
            subtotal_snapshot=300,
        )
        OrderItem.objects.create(
            order=order,
            variant=self.catalog.variant,
            quantity=2,
            unit_price_snapshot=150,
            line_total_snapshot=300,
            product_name_snapshot="Snapshot Hoodie",
            color_name_snapshot="Snapshot Black",
            size_name_snapshot="Snapshot M",
        )
        self.catalog.product.name = "Renamed Product"
        self.catalog.product.save(update_fields=["name"])

        message = build_order_message(order)

        self.assertIn(f"#{order.pk}", message)
        self.assertIn("Ivan Ivanov", message)
        self.assertIn("ivan@example.com", message)
        self.assertIn("+79990000000", message)
        self.assertIn("Moscow", message)
        self.assertIn("Tverskaya", message)
        self.assertIn("10", message)
        self.assertIn("15", message)
        self.assertIn("123456", message)
        self.assertIn("Call before delivery", message)
        self.assertIn("Snapshot Hoodie", message)
        self.assertIn("Snapshot Black", message)
        self.assertIn("Snapshot M", message)
        self.assertIn("2", message)
        self.assertIn("300", message)
        self.assertNotIn("Renamed Product", message)


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

    def add_catalog_item_to_cart(self, quantity: int = 2) -> None:
        session = self.client.session
        session["cart"] = [
            {
                "variant_id": str(self.catalog.variant.id),
                "quantity": quantity,
            }
        ]
        session.save()

    def post_valid_checkout(self):
        return self.client.post(
            reverse("orders:checkout"),
            data={
                "customer_name": "Ivan Ivanov",
                "customer_email": "ivan@example.com",
                "customer_phone": "+79990000000",
                "delivery_city": "Moscow",
                "delivery_street": "Tverskaya",
                "delivery_house": "10",
                "delivery_apartment": "15",
                "delivery_postal_code": "123456",
                "delivery_comment": "Call before delivery",
            },
        )

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

    @override_settings(
        TELEGRAM_NOTIFICATIONS_ENABLED=True,
        TELEGRAM_MANAGER_CHAT_IDS=["111", "222"],
        TELEGRAM_NOTIFICATION_RETRY_MINUTES=5,
    )
    def test_checkout_creates_telegram_notifications_for_manager_chat_ids(self):
        """Checkout should enqueue one Telegram notification per manager chat id."""
        self.add_catalog_item_to_cart()
        min_next_attempt_at = timezone.now() + timedelta(minutes=5)

        response = self.post_valid_checkout()

        max_next_attempt_at = timezone.now() + timedelta(minutes=5)
        order = Order.objects.get()
        notifications = list(order.telegram_notifications.order_by("chat_id"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(notifications), 2)
        self.assertEqual([notification.chat_id for notification in notifications], ["111", "222"])
        for notification in notifications:
            self.assertEqual(notification.status, TelegramNotificationStatus.PENDING)
            self.assertEqual(notification.attempts, 0)
            self.assertEqual(notification.last_error, "")
            self.assertIsNone(notification.sent_at)
            self.assertGreaterEqual(notification.next_attempt_at, min_next_attempt_at)
            self.assertLessEqual(notification.next_attempt_at, max_next_attempt_at)

    @override_settings(
        TELEGRAM_NOTIFICATIONS_ENABLED=False,
        TELEGRAM_MANAGER_CHAT_IDS=["111"],
        TELEGRAM_NOTIFICATION_RETRY_MINUTES=5,
    )
    def test_checkout_does_not_create_telegram_notifications_when_disabled(self):
        """Disabled Telegram notifications must not block checkout or create outbox rows."""
        self.add_catalog_item_to_cart()

        response = self.post_valid_checkout()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(TelegramNotification.objects.count(), 0)

    @override_settings(
        TELEGRAM_NOTIFICATIONS_ENABLED=True,
        TELEGRAM_MANAGER_CHAT_IDS=[],
        TELEGRAM_NOTIFICATION_RETRY_MINUTES=5,
    )
    def test_checkout_does_not_create_telegram_notifications_without_chat_ids(self):
        """Checkout should skip outbox rows when no manager chat ids are configured."""
        self.add_catalog_item_to_cart()

        response = self.post_valid_checkout()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(TelegramNotification.objects.count(), 0)


class TelegramNotificationCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.catalog = create_catalog_fixture(suffix="telegram-command")

    def create_order(self) -> Order:
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
            subtotal_snapshot=100,
        )
        OrderItem.objects.create(
            order=order,
            variant=self.catalog.variant,
            quantity=1,
            unit_price_snapshot=100,
            line_total_snapshot=100,
            product_name_snapshot=self.catalog.product.name,
            color_name_snapshot=self.catalog.color.name,
            size_name_snapshot=self.catalog.size.name,
        )
        return order

    def create_notification(
        self,
        *,
        order: Order | None = None,
        chat_id: str = "111",
        status: str = TelegramNotificationStatus.PENDING,
        attempts: int = 0,
        next_attempt_at=None,
        sent_at=None,
        last_error: str = "",
    ) -> TelegramNotification:
        if order is None:
            order = self.create_order()

        if next_attempt_at is None:
            next_attempt_at = timezone.now() - timedelta(minutes=1)

        return TelegramNotification.objects.create(
            order=order,
            chat_id=chat_id,
            status=status,
            attempts=attempts,
            next_attempt_at=next_attempt_at,
            sent_at=sent_at,
            last_error=last_error,
        )

    @override_settings(TELEGRAM_NOTIFICATION_RETRY_MINUTES=10)
    @patch("orders.management.commands.process_telegram_notifications.send_order_notification")
    @patch(
        "orders.management.commands.process_telegram_notifications.build_order_message",
        return_value="Telegram order text",
    )
    def test_process_due_pending_notification_marks_sent(
        self,
        build_order_message_mock,
        send_order_notification_mock,
    ):
        """Due pending notification should be sent and marked as sent."""
        notification = self.create_notification()

        call_command("process_telegram_notifications")

        notification.refresh_from_db()
        build_order_message_mock.assert_called_once()
        send_order_notification_mock.assert_called_once_with("111", "Telegram order text")
        self.assertEqual(notification.status, TelegramNotificationStatus.SENT)
        self.assertIsNotNone(notification.sent_at)
        self.assertEqual(notification.last_error, "")

    @override_settings(TELEGRAM_NOTIFICATION_RETRY_MINUTES=10)
    @patch(
        "orders.management.commands.process_telegram_notifications.send_order_notification",
        side_effect=RuntimeError("Telegram is unavailable"),
    )
    @patch(
        "orders.management.commands.process_telegram_notifications.build_order_message",
        return_value="Telegram order text",
    )
    def test_process_due_notification_failure_schedules_retry(
        self,
        build_order_message_mock,
        send_order_notification_mock,
    ):
        """Failed send should store the error, increment attempts, and move retry time."""
        notification = self.create_notification(attempts=2)
        min_next_attempt_at = timezone.now() + timedelta(minutes=10)

        call_command("process_telegram_notifications")

        max_next_attempt_at = timezone.now() + timedelta(minutes=10)
        notification.refresh_from_db()
        build_order_message_mock.assert_called_once()
        send_order_notification_mock.assert_called_once_with("111", "Telegram order text")
        self.assertEqual(notification.status, TelegramNotificationStatus.FAILED)
        self.assertEqual(notification.attempts, 3)
        self.assertIn("Telegram is unavailable", notification.last_error)
        self.assertIsNone(notification.sent_at)
        self.assertGreaterEqual(notification.next_attempt_at, min_next_attempt_at)
        self.assertLessEqual(notification.next_attempt_at, max_next_attempt_at)

    @patch("orders.management.commands.process_telegram_notifications.send_order_notification")
    @patch("orders.management.commands.process_telegram_notifications.build_order_message")
    def test_sent_notification_is_not_retried(
        self,
        build_order_message_mock,
        send_order_notification_mock,
    ):
        """Already sent notification should not be picked up for retry."""
        sent_at = timezone.now() - timedelta(minutes=5)
        notification = self.create_notification(
            status=TelegramNotificationStatus.SENT,
            sent_at=sent_at,
        )

        call_command("process_telegram_notifications")

        notification.refresh_from_db()
        build_order_message_mock.assert_not_called()
        send_order_notification_mock.assert_not_called()
        self.assertEqual(notification.status, TelegramNotificationStatus.SENT)
        self.assertEqual(notification.sent_at, sent_at)

    @override_settings(TELEGRAM_NOTIFICATION_RETRY_MINUTES=10)
    @patch("orders.management.commands.process_telegram_notifications.send_order_notification")
    @patch(
        "orders.management.commands.process_telegram_notifications.build_order_message",
        return_value="Telegram order text",
    )
    def test_one_chat_id_failure_does_not_stop_second_notification(
        self,
        build_order_message_mock,
        send_order_notification_mock,
    ):
        """Failure for one chat id should not stop the next due notification."""
        order = self.create_order()
        failed_notification = self.create_notification(order=order, chat_id="111")
        sent_notification = self.create_notification(order=order, chat_id="222")

        def send_side_effect(chat_id, text):
            if chat_id == "111":
                raise RuntimeError("First chat failed")

        send_order_notification_mock.side_effect = send_side_effect

        call_command("process_telegram_notifications")

        failed_notification.refresh_from_db()
        sent_notification.refresh_from_db()
        self.assertEqual(build_order_message_mock.call_count, 2)
        self.assertEqual(send_order_notification_mock.call_count, 2)
        self.assertEqual(failed_notification.status, TelegramNotificationStatus.FAILED)
        self.assertEqual(failed_notification.attempts, 1)
        self.assertIn("First chat failed", failed_notification.last_error)
        self.assertEqual(sent_notification.status, TelegramNotificationStatus.SENT)
        self.assertIsNotNone(sent_notification.sent_at)
