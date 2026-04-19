from .cart import Cart


def cart_state(request):
    """Контекстный процессор для добавления состояния корзины в шаблоны."""
    return {"cart_state": Cart(request)}
