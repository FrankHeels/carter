from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods, require_GET

from cart.cart import Cart
from orders.models import Order
from .forms import GuestCheckForm
from .services import place_order_from_cart, EmptyCartError, CartChangedError


def _build_checkout_context(cart: Cart, form: GuestCheckForm) -> dict[str, object]:
    return {"form": form, "cart": cart}


def _render_checkout(request, cart: Cart, form: GuestCheckForm, status: int = 200):
    context = _build_checkout_context(cart, form)
    return render(request, "orders/checkout.html", context, status=status)


@require_http_methods(["GET", "POST"])
def checkout(request):
    """Обработка страницы оформления заказа"""
    cart = Cart(request)
    # GET
    if request.method == "GET":
        if not len(cart):
            return redirect("cart_detail")

        form = GuestCheckForm()
        return _render_checkout(request, cart, form)

    # POST
    form = GuestCheckForm(request.POST)

    if not form.is_valid():
        return _render_checkout(request, cart, form, status=400)

    try:
        order = place_order_from_cart(cart, form.cleaned_data)
    except EmptyCartError:
        form.add_error(None, "Корзина пуста")
        return _render_checkout(request, Cart(request), form, status=409)
    except CartChangedError:
        form.add_error(None, "Корзина изменилась. Проверьте состав заказа еще раз.")
        return _render_checkout(request, Cart(request), form, status=409)

    request.session["last_order_id"] = order.id
    return redirect("orders:success")


@require_GET
def success(request):
    """Отображение страницы успешного оформления заказа"""
    last_order_id = request.session.pop("last_order_id", None)

    if last_order_id is None:
        return redirect("cart_detail")

    order = Order.objects.prefetch_related("items").filter(pk=last_order_id).first()
    if order is None:
        return redirect("cart_detail")

    return render(request, "orders/success.html", {"order": order})
