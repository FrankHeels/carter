from __future__ import annotations

from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse

from cart.cart import Cart
from shop.models import Category, Color, Product, ProductImage, ProductVariant, Size


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


class CartTestDataMixin:
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.primary = create_catalog_fixture(
            suffix="primary",
            price=100,
            size_name="M",
            size_order=1,
            color_name="Black",
            hex_code="#111111",
        )
        cls.secondary = create_catalog_fixture(
            suffix="secondary",
            price=250,
            size_name="L",
            size_order=2,
            color_name="White",
            hex_code="#FFFFFF",
        )
        cls.tertiary = create_catalog_fixture(
            suffix="tertiary",
            price=400,
            size_name="S",
            size_order=3,
            color_name="Blue",
            hex_code="#0000FF",
        )


class CartCoreTests(CartTestDataMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.factory = RequestFactory()

    def build_request(self, session_cart: list[dict[str, int | str | None]] | None = None):
        request = self.factory.get("/cart/")
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()

        if session_cart is not None:
            request.session[Cart.CART_SESSION_KEY] = [dict(item) for item in session_cart]
            request.session.save()

        return request

    def build_cart(self, session_cart: list[dict[str, int | str | None]] | None = None):
        request = self.build_request(session_cart=session_cart)
        return request, Cart(request)

    def assert_runtime_items(self, items, expected):
        self.assertEqual(
            [
                (
                    item["variant_id"],
                    item["quantity"],
                    item["variant"],
                    item["total_price"],
                )
                for item in items
            ],
            [
                (
                    str(variant.id),
                    quantity,
                    variant,
                    variant.product.price * quantity,
                )
                for variant, quantity in expected
            ],
        )

    def test_add_new_variant_creates_cart_line(self):
        request, cart = self.build_cart()

        cart.add(self.primary.variant)

        self.assertEqual(
            request.session[Cart.CART_SESSION_KEY],
            [{"variant_id": str(self.primary.variant.id), "quantity": 1}],
        )

    def test_add_existing_variant_increases_quantity(self):
        request, cart = self.build_cart()

        cart.add(self.primary.variant, quantity=2)
        cart.add(self.primary.variant, quantity=3)

        self.assertEqual(
            request.session[Cart.CART_SESSION_KEY],
            [{"variant_id": str(self.primary.variant.id), "quantity": 5}],
        )

    def test_add_unavailable_variant_does_not_create_cart_line(self):
        self.primary.variant.stock = 0
        self.primary.variant.save(update_fields=["stock"])
        request, cart = self.build_cart()

        cart.add(self.primary.variant, quantity=1)

        self.assertEqual(request.session[Cart.CART_SESSION_KEY], [])

    def test_add_clamps_quantity_to_current_stock(self):
        self.primary.variant.stock = 3
        self.primary.variant.save(update_fields=["stock"])
        request, cart = self.build_cart()

        cart.add(self.primary.variant, quantity=10)

        self.assertEqual(
            request.session[Cart.CART_SESSION_KEY],
            [{"variant_id": str(self.primary.variant.id), "quantity": 3}],
        )

    def test_len_returns_total_quantity_from_runtime_items(self):
        _, cart = self.build_cart(
            session_cart=[
                {"variant_id": str(self.primary.variant.id), "quantity": 2},
                {"variant_id": str(self.secondary.variant.id), "quantity": 4},
            ]
        )

        self.assertEqual(len(cart), 6)

    def test_len_self_heals_quantity_when_stock_drops(self):
        self.primary.variant.stock = 2
        self.primary.variant.save(update_fields=["stock"])
        request, cart = self.build_cart(
            session_cart=[{"variant_id": str(self.primary.variant.id), "quantity": 5}]
        )

        self.assertEqual(len(cart), 2)
        self.assertEqual(
            request.session[Cart.CART_SESSION_KEY],
            [{"variant_id": str(self.primary.variant.id), "quantity": 2}],
        )

    def test_increment_changes_quantity_for_existing_variant(self):
        request, cart = self.build_cart(
            session_cart=[{"variant_id": str(self.primary.variant.id), "quantity": 2}]
        )

        cart.increment(self.primary.variant)

        self.assertEqual(
            request.session[Cart.CART_SESSION_KEY],
            [{"variant_id": str(self.primary.variant.id), "quantity": 3}],
        )

    def test_increment_does_not_exceed_variant_stock(self):
        self.primary.variant.stock = 3
        self.primary.variant.save(update_fields=["stock"])
        request, cart = self.build_cart(
            session_cart=[{"variant_id": str(self.primary.variant.id), "quantity": 3}]
        )

        cart.increment(self.primary.variant)

        self.assertEqual(
            request.session[Cart.CART_SESSION_KEY],
            [{"variant_id": str(self.primary.variant.id), "quantity": 3}],
        )

    def test_increment_removes_variant_when_it_becomes_unavailable(self):
        request, cart = self.build_cart(
            session_cart=[{"variant_id": str(self.primary.variant.id), "quantity": 1}]
        )
        self.primary.variant.stock = 0
        self.primary.variant.save(update_fields=["stock"])

        cart.increment(self.primary.variant)

        self.assertEqual(request.session[Cart.CART_SESSION_KEY], [])

    def test_decrement_changes_quantity_for_existing_variant(self):
        request, cart = self.build_cart(
            session_cart=[{"variant_id": str(self.primary.variant.id), "quantity": 4}]
        )

        cart.decrement(self.primary.variant)

        self.assertEqual(
            request.session[Cart.CART_SESSION_KEY],
            [{"variant_id": str(self.primary.variant.id), "quantity": 3}],
        )

    def test_decrement_clamps_quantity_to_minimum_one(self):
        request, cart = self.build_cart(
            session_cart=[{"variant_id": str(self.primary.variant.id), "quantity": 1}]
        )

        cart.decrement(self.primary.variant)

        self.assertEqual(
            request.session[Cart.CART_SESSION_KEY],
            [{"variant_id": str(self.primary.variant.id), "quantity": 1}],
        )

    def test_remove_deletes_variant_from_cart(self):
        request, cart = self.build_cart(
            session_cart=[
                {"variant_id": str(self.primary.variant.id), "quantity": 2},
                {"variant_id": str(self.secondary.variant.id), "quantity": 1},
            ]
        )

        cart.remove(self.primary.variant)

        self.assertEqual(
            request.session[Cart.CART_SESSION_KEY],
            [{"variant_id": str(self.secondary.variant.id), "quantity": 1}],
        )

    def test_clear_empties_cart(self):
        request, cart = self.build_cart(
            session_cart=[{"variant_id": str(self.primary.variant.id), "quantity": 2}]
        )

        cart.clear()

        self.assertEqual(cart.cart, [])
        self.assertEqual(request.session[Cart.CART_SESSION_KEY], [])

    def test_iter_returns_runtime_items_with_variant_and_total_price(self):
        _, cart = self.build_cart(
            session_cart=[{"variant_id": str(self.primary.variant.id), "quantity": 3}]
        )

        items = list(cart)

        self.assert_runtime_items(items, [(self.primary.variant, 3)])

    def test_get_total_price_sums_all_runtime_items(self):
        _, cart = self.build_cart(
            session_cart=[
                {"variant_id": str(self.primary.variant.id), "quantity": 2},
                {"variant_id": str(self.secondary.variant.id), "quantity": 3},
            ]
        )

        self.assertEqual(cart.get_total_price(), 950)

    def test_iter_skips_deleted_variant_and_cleans_session(self):
        request, cart = self.build_cart(
            session_cart=[{"variant_id": str(self.primary.variant.id), "quantity": 2}]
        )
        self.primary.variant.delete()

        items = list(cart)

        self.assertEqual(items, [])
        self.assertEqual(request.session[Cart.CART_SESSION_KEY], [])

    def test_iter_skips_unavailable_variant_and_cleans_session(self):
        request, cart = self.build_cart(
            session_cart=[{"variant_id": str(self.primary.variant.id), "quantity": 2}]
        )
        self.primary.variant.stock = 0
        self.primary.variant.save(update_fields=["stock"])

        items = list(cart)

        self.assertEqual(items, [])
        self.assertEqual(request.session[Cart.CART_SESSION_KEY], [])

    def test_iter_skips_invalid_quantity_values(self):
        request, cart = self.build_cart(
            session_cart=[
                {"variant_id": str(self.primary.variant.id), "quantity": "abc"},
                {"variant_id": str(self.secondary.variant.id), "quantity": None},
                {"variant_id": str(self.tertiary.variant.id), "quantity": 2},
            ]
        )

        items = list(cart)

        self.assert_runtime_items(items, [(self.tertiary.variant, 2)])
        self.assertEqual(
            request.session[Cart.CART_SESSION_KEY],
            [{"variant_id": str(self.tertiary.variant.id), "quantity": 2}],
        )

    def test_iter_skips_zero_or_negative_quantity(self):
        request, cart = self.build_cart(
            session_cart=[
                {"variant_id": str(self.primary.variant.id), "quantity": 0},
                {"variant_id": str(self.secondary.variant.id), "quantity": -5},
                {"variant_id": str(self.tertiary.variant.id), "quantity": 3},
            ]
        )

        items = list(cart)

        self.assert_runtime_items(items, [(self.tertiary.variant, 3)])
        self.assertEqual(
            request.session[Cart.CART_SESSION_KEY],
            [{"variant_id": str(self.tertiary.variant.id), "quantity": 3}],
        )

    def test_iter_clamps_quantity_to_current_stock(self):
        self.primary.variant.stock = 2
        self.primary.variant.save(update_fields=["stock"])
        request, cart = self.build_cart(
            session_cart=[{"variant_id": str(self.primary.variant.id), "quantity": 5}]
        )

        items = list(cart)

        self.assert_runtime_items(items, [(self.primary.variant, 2)])
        self.assertEqual(
            request.session[Cart.CART_SESSION_KEY],
            [{"variant_id": str(self.primary.variant.id), "quantity": 2}],
        )

    def test_save_invalidates_runtime_cache_after_mutation(self):
        scenarios = [
            {
                "name": "add",
                "initial_cart": [{"variant_id": str(self.primary.variant.id), "quantity": 1}],
                "mutate": lambda cart: cart.add(self.secondary.variant, quantity=2),
                "expected": [
                    (self.primary.variant, 1),
                    (self.secondary.variant, 2),
                ],
            },
            {
                "name": "increment",
                "initial_cart": [{"variant_id": str(self.primary.variant.id), "quantity": 1}],
                "mutate": lambda cart: cart.increment(self.primary.variant),
                "expected": [(self.primary.variant, 2)],
            },
            {
                "name": "remove",
                "initial_cart": [
                    {"variant_id": str(self.primary.variant.id), "quantity": 1},
                    {"variant_id": str(self.secondary.variant.id), "quantity": 1},
                ],
                "mutate": lambda cart: cart.remove(self.primary.variant),
                "expected": [(self.secondary.variant, 1)],
            },
            {
                "name": "clear",
                "initial_cart": [{"variant_id": str(self.primary.variant.id), "quantity": 1}],
                "mutate": lambda cart: cart.clear(),
                "expected": [],
            },
        ]

        for scenario in scenarios:
            with self.subTest(action=scenario["name"]):
                request, cart = self.build_cart(session_cart=scenario["initial_cart"])

                self.assertTrue(list(cart))

                scenario["mutate"](cart)

                items = list(cart)

                self.assert_runtime_items(items, scenario["expected"])
                self.assertEqual(
                    request.session[Cart.CART_SESSION_KEY],
                    [
                        {"variant_id": str(variant.id), "quantity": quantity}
                        for variant, quantity in scenario["expected"]
                    ],
                )


class CartViewTests(CartTestDataMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client.raise_request_exception = False

    def cart_session(self):
        return self.client.session.get(Cart.CART_SESSION_KEY, [])

    def set_cart_session(self, items):
        session = self.client.session
        session[Cart.CART_SESSION_KEY] = [dict(item) for item in items]
        session.save()

    def product_detail_url(self):
        return reverse("product_detail", args=[self.primary.product.slug])

    def test_cart_detail_returns_200(self):
        response = self.client.get(reverse("cart_detail"))

        self.assertEqual(response.status_code, 200)

    def test_cart_detail_uses_cart_template(self):
        response = self.client.get(reverse("cart_detail"))

        self.assertTemplateUsed(response, "cart/cart.html")

    def test_cart_detail_exposes_cart_in_context(self):
        response = self.client.get(reverse("cart_detail"))

        self.assertIsNotNone(response.context)
        self.assertIn("cart", response.context)
        self.assertIsInstance(response.context["cart"], Cart)

    def test_product_detail_renders_add_to_cart_form_shell(self):
        response = self.client.get(self.product_detail_url())

        self.assertContains(response, 'id="add-to-cart-form"', html=False)
        self.assertContains(response, 'name="next"', html=False)
        self.assertContains(response, 'name="open_cart" value="0"', html=False)
        self.assertContains(response, 'id="add-to-cart-submit"', html=False)

    def test_product_detail_keeps_drawer_closed_after_add_to_cart(self):
        response = self.client.get(self.product_detail_url())

        self.assertNotContains(response, 'name="open_cart" value="1"', html=False)
        self.assertNotContains(response, "preview", html=False)

    def test_product_detail_exposes_global_cart_state_in_layout(self):
        self.set_cart_session([{"variant_id": str(self.primary.variant.id), "quantity": 3}])

        response = self.client.get(self.product_detail_url())

        self.assertIn("cart_state", response.context)
        self.assertIsInstance(response.context["cart_state"], Cart)
        self.assertContains(response, "Корзина")
        self.assertContains(response, ">3<", html=False)
        self.assertContains(response, 'data-cart-trigger', html=False)
        self.assertContains(response, 'data-cart-page-link', html=False)
        self.assertContains(response, 'href="%s"' % reverse("cart_detail"), html=False)

    def test_shop_layout_renders_cart_preview_from_session_state(self):
        ProductImage.objects.create(
            product=self.primary.product,
            color=self.primary.color,
            image=SimpleUploadedFile(
                "primary-drawer.jpg",
                b"drawer-image-bytes",
                content_type="image/jpeg",
            ),
            is_main=True,
        )
        self.set_cart_session([
            {"variant_id": str(self.primary.variant.id), "quantity": 2},
            {"variant_id": str(self.secondary.variant.id), "quantity": 1},
        ])

        response = self.client.get(reverse("product_list"))

        self.assertContains(response, self.primary.product.name)
        self.assertContains(response, self.primary.color.name)
        self.assertContains(response, self.primary.size.name)
        self.assertContains(response, self.secondary.product.name)
        self.assertContains(response, "450", html=False)
        self.assertContains(response, 'href="%s"' % reverse("cart_detail"), html=False)
        self.assertContains(response, 'data-drawer-item', html=False)
        self.assertContains(response, 'data-drawer-quantity', html=False)
        self.assertContains(response, 'data-drawer-line-total', html=False)
        self.assertContains(response, "window.CarterCartUI", html=False)
        self.assertContains(response, 'id="cart-overlay"', html=False)
        self.assertContains(response, 'id="close-cart-btn"', html=False)
        self.assertContains(response, 'cartOverlay?.addEventListener("click", closeCart);', html=False)
        self.assertContains(response, 'id="main-header"', html=False)
        self.assertContains(response, 'z-30', html=False)
        self.assertContains(response, 'id="cart-overlay" class="fixed inset-0 z-40', html=False)
        self.assertContains(response, 'id="cart-drawer" class="fixed inset-y-0 right-0 z-50', html=False)
        self.assertContains(
            response,
            self.primary.product.get_main_image().image.url,
            html=False,
        )

    def test_cart_add_post_adds_variant_and_redirects(self):
        response = self.client.post(
            reverse("cart_add", args=[self.primary.variant.id]),
            {"quantity": 2},
        )

        self.assertRedirects(response, reverse("cart_detail"), fetch_redirect_response=False)
        self.assertEqual(
            self.cart_session(),
            [{"variant_id": str(self.primary.variant.id), "quantity": 2}],
        )

    def test_cart_add_redirects_back_to_product_with_open_marker(self):
        response = self.client.post(
            reverse("cart_add", args=[self.primary.variant.id]),
            {
                "quantity": 2,
                "next": self.product_detail_url(),
                "open_cart": "1",
            },
        )

        self.assertRedirects(
            response,
            f"{self.product_detail_url()}?cart=open",
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.cart_session(),
            [{"variant_id": str(self.primary.variant.id), "quantity": 2}],
        )

    def test_cart_add_redirects_back_to_product_without_open_marker_when_disabled(self):
        response = self.client.post(
            reverse("cart_add", args=[self.primary.variant.id]),
            {
                "quantity": 2,
                "next": self.product_detail_url(),
                "open_cart": "0",
            },
        )

        self.assertRedirects(
            response,
            self.product_detail_url(),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.cart_session(),
            [{"variant_id": str(self.primary.variant.id), "quantity": 2}],
        )

    def test_cart_add_get_returns_405(self):
        response = self.client.get(reverse("cart_add", args=[self.primary.variant.id]))

        self.assertEqual(response.status_code, 405)

    def test_cart_add_with_invalid_quantity_defaults_to_one(self):
        response = self.client.post(
            reverse("cart_add", args=[self.primary.variant.id]),
            {"quantity": "abc"},
        )

        self.assertRedirects(response, reverse("cart_detail"), fetch_redirect_response=False)
        self.assertEqual(
            self.cart_session(),
            [{"variant_id": str(self.primary.variant.id), "quantity": 1}],
        )

    def test_cart_add_returns_404_for_missing_variant(self):
        response = self.client.post(reverse("cart_add", args=[999999]), {"quantity": 1})

        self.assertEqual(response.status_code, 404)

    def test_cart_add_does_not_persist_unavailable_variant(self):
        self.primary.variant.stock = 0
        self.primary.variant.save(update_fields=["stock"])

        response = self.client.post(
            reverse("cart_add", args=[self.primary.variant.id]),
            {"quantity": 1},
        )

        self.assertRedirects(response, reverse("cart_detail"), fetch_redirect_response=False)
        self.assertEqual(self.cart_session(), [])

    def test_cart_add_clamps_quantity_to_variant_stock(self):
        self.primary.variant.stock = 3
        self.primary.variant.save(update_fields=["stock"])

        response = self.client.post(
            reverse("cart_add", args=[self.primary.variant.id]),
            {"quantity": 10},
        )

        self.assertRedirects(response, reverse("cart_detail"), fetch_redirect_response=False)
        self.assertEqual(
            self.cart_session(),
            [{"variant_id": str(self.primary.variant.id), "quantity": 3}],
        )

    def test_cart_update_ajax_increment_returns_json_payload(self):
        self.set_cart_session([{"variant_id": str(self.primary.variant.id), "quantity": 1}])

        response = self.client.post(
            reverse("cart_update", args=[self.primary.variant.id]),
            {"action": "increment"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(
            response.json(),
            {
                "variant_id": self.primary.variant.id,
                "quantity": 2,
                "line_total": 200,
                "cart_count": 2,
                "cart_subtotal": 200,
                "can_increment": True,
                "can_decrement": True,
            },
        )
        self.assertEqual(
            self.cart_session(),
            [{"variant_id": str(self.primary.variant.id), "quantity": 2}],
        )

    def test_cart_update_accepts_stepper_action_post_field(self):
        self.set_cart_session([{"variant_id": str(self.primary.variant.id), "quantity": 1}])

        response = self.client.post(
            reverse("cart_update", args=[self.primary.variant.id]),
            {"stepper_action": "increment"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["quantity"], 2)

    def test_cart_update_ajax_decrement_returns_json_payload(self):
        self.set_cart_session([{"variant_id": str(self.primary.variant.id), "quantity": 2}])

        response = self.client.post(
            reverse("cart_update", args=[self.primary.variant.id]),
            {"action": "decrement"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(
            response.json(),
            {
                "variant_id": self.primary.variant.id,
                "quantity": 1,
                "line_total": 100,
                "cart_count": 1,
                "cart_subtotal": 100,
                "can_increment": True,
                "can_decrement": False,
            },
        )
        self.assertEqual(
            self.cart_session(),
            [{"variant_id": str(self.primary.variant.id), "quantity": 1}],
        )

    def test_cart_update_ajax_self_heals_when_variant_becomes_unavailable(self):
        self.set_cart_session([{"variant_id": str(self.primary.variant.id), "quantity": 1}])
        self.primary.variant.stock = 0
        self.primary.variant.save(update_fields=["stock"])

        response = self.client.post(
            reverse("cart_update", args=[self.primary.variant.id]),
            {"action": "increment"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "variant_id": self.primary.variant.id,
                "quantity": 0,
                "line_total": 0,
                "cart_count": 0,
                "cart_subtotal": 0,
                "can_increment": False,
                "can_decrement": False,
            },
        )
        self.assertEqual(self.cart_session(), [])

    def test_cart_update_get_returns_405(self):
        response = self.client.get(reverse("cart_update", args=[self.primary.variant.id]))

        self.assertEqual(response.status_code, 405)

    def test_cart_update_returns_404_for_missing_variant(self):
        response = self.client.post(reverse("cart_update", args=[999999]), {"action": "increment"})

        self.assertEqual(response.status_code, 404)

    def test_cart_update_rejects_invalid_action(self):
        self.set_cart_session([{"variant_id": str(self.primary.variant.id), "quantity": 1}])

        response = self.client.post(
            reverse("cart_update", args=[self.primary.variant.id]),
            {"action": "replace"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)

    def test_cart_remove_post_removes_variant_and_redirects(self):
        self.set_cart_session([{"variant_id": str(self.primary.variant.id), "quantity": 2}])

        response = self.client.post(reverse("cart_remove", args=[self.primary.variant.id]))

        self.assertRedirects(response, reverse("cart_detail"), fetch_redirect_response=False)
        self.assertEqual(self.cart_session(), [])

    def test_cart_remove_get_returns_405(self):
        response = self.client.get(reverse("cart_remove", args=[self.primary.variant.id]))

        self.assertEqual(response.status_code, 405)

    def test_cart_remove_returns_404_for_missing_variant(self):
        response = self.client.post(reverse("cart_remove", args=[999999]))

        self.assertEqual(response.status_code, 404)

    def test_cart_clear_post_empties_cart_and_redirects(self):
        self.set_cart_session([{"variant_id": str(self.primary.variant.id), "quantity": 2}])

        response = self.client.post(reverse("cart_clear"))

        self.assertRedirects(response, reverse("cart_detail"), fetch_redirect_response=False)
        self.assertEqual(self.cart_session(), [])

    def test_cart_clear_get_returns_405(self):
        response = self.client.get(reverse("cart_clear"))

        self.assertEqual(response.status_code, 405)

    def test_cart_detail_empty_state_renders_catalog_cta(self):
        response = self.client.get(reverse("cart_detail"))

        self.assertContains(response, "Корзина пуста")
        self.assertContains(response, 'href="%s"' % reverse("product_list"), html=False)

    def test_cart_detail_renders_stepper_controls_and_subtotal(self):
        self.set_cart_session([
            {"variant_id": str(self.primary.variant.id), "quantity": 2},
        ])

        response = self.client.get(reverse("cart_detail"))

        self.assertContains(response, self.primary.product.name)
        self.assertContains(response, self.primary.color.name)
        self.assertContains(response, self.primary.size.name)
        self.assertContains(
            response,
            'action="%s"' % reverse("cart_update", args=[self.primary.variant.id]),
            html=False,
        )
        self.assertContains(response, 'data-cart-item', html=False)
        self.assertContains(response, 'data-cart-stepper', html=False)
        self.assertContains(response, 'data-cart-quantity', html=False)
        self.assertContains(response, 'data-cart-line-total', html=False)
        self.assertContains(response, 'data-stepper-button="decrement"', html=False)
        self.assertContains(response, 'data-stepper-button="increment"', html=False)
        self.assertContains(response, 'name="stepper_action"', html=False)
        self.assertNotContains(response, 'name="action"', html=False)
        self.assertContains(response, 'fetch(form.getAttribute("action")', html=False)
        self.assertContains(
            response,
            'action="%s"' % reverse("cart_remove", args=[self.primary.variant.id]),
            html=False,
        )
        self.assertContains(response, 'action="%s"' % reverse("cart_clear"), html=False)
        self.assertNotContains(response, 'type="number"', html=False)
        self.assertNotContains(response, "Обновить")
        self.assertContains(response, "200", html=False)
