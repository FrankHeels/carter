from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.http import HttpRequest, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST
from shop.models import ProductVariant
from .cart import Cart

def _parse_quantity(request: HttpRequest, default: int = 1) -> int:
    quantity = request.POST.get("quantity", default)

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        return default
    
    return max(quantity, 1)

def _append_query_param(url: str, key: str, value: str) -> str:
    """Добавляет или обновляет параметр в URL."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query),
        parts.fragment,
    ))

def _build_cart_add_redirect(request: HttpRequest):
    """Определяет, куда перенаправить пользователя после добавления товара в корзину:
        - Если в POST-запросе есть валидный параметр `next`, перенаправляет на него.
        - Иначе — на страницу корзины."""
    next_url = request.POST.get("next")
    should_open_cart = request.POST.get("open_cart") == "1"

    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        target_url = next_url
        if should_open_cart:
            target_url = _append_query_param(target_url, "cart", "open")
        return redirect(target_url)

    return redirect("cart_detail")


def _parse_cart_action(request: HttpRequest) -> str | None:
    action = request.POST.get("stepper_action") or request.POST.get("action")
    if action in {"increment", "decrement"}:
        return action
    return None

def _build_stepper_payload(cart: Cart, variant: ProductVariant) -> dict[str, object]:
    """Строит полезную нагрузку для ответа на AJAX-запрос при обновлении количества товара в корзине."""
    quantity = cart.get_quantity(variant)

    return {
        "variant_id": variant.id,
        "quantity": quantity,
        "line_total": variant.product.price * quantity,
        "cart_count": len(cart),
        "cart_subtotal": cart.get_total_price(),
        "can_increment": quantity < variant.stock,
        "can_decrement": quantity > 1,
    }

@require_GET
def cart_detail(request):
    """Отображение содержимого корзины."""
    cart = Cart(request)
    return render(request, 'cart/cart.html', {'cart': cart})

@require_POST
def cart_add(request, variant_id):
    cart = Cart(request)
    variant = get_object_or_404(ProductVariant, id=variant_id)
    quantity = _parse_quantity(request)
    
    cart.add(variant, quantity)
    return _build_cart_add_redirect(request)

@require_POST
def cart_remove(request, variant_id):
    cart = Cart(request)
    variant = get_object_or_404(ProductVariant, id=variant_id)

    cart.remove(variant)
    return redirect('cart_detail')

@require_POST
def cart_update(request, variant_id):
    cart = Cart(request)
    variant = get_object_or_404(ProductVariant, id=variant_id)
    
    action = _parse_cart_action(request)

    if action is None:
        return JsonResponse({"detail": "Invalid action."}, status=400)
    
    if action == "increment":
        cart.increment(variant)
    else:
        cart.decrement(variant)

    # Если это AJAX-запрос, возвращаем JSON с обновленными данными корзины, иначе — перенаправляем на страницу корзины.
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(_build_stepper_payload(cart, variant))

    return redirect("cart_detail")

@require_POST
def cart_clear(request):
    Cart(request).clear()
    return redirect('cart_detail')
