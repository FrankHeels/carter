import json
import urllib.request
from django.conf import settings
from orders.models import Order

def build_order_message(order: Order) -> str:
    lines = [
        f"Новый заказ #{order.pk}",
        f"Статус: {order.get_status_display()}",
        f"Имя: {order.customer_name}",
        f"Email: {order.customer_email}",
        f"Телефон: {order.customer_phone}",
        "Доставка:",
        f"  Город: {order.delivery_city}",
        f"  Улица: {order.delivery_street}",
        f"  Дом: {order.delivery_house}",
    ]

    if order.delivery_apartment:
        lines.append(f"Квартира/офис: {order.delivery_apartment}")

    lines.append(f"Почтовый индекс: {order.delivery_postal_code}")

    if order.delivery_comment:
        lines.append(f"Комментарий к доставке: {order.delivery_comment}")

    lines.append("Товары:")

    for item in order.items.all().order_by("pk"):
        lines.append(
            f"  - {item.product_name_snapshot} "
            f"(цвет: {item.color_name_snapshot}, размер: {item.size_name_snapshot}) "
            f"Количество: {item.quantity}, Сумма: {item.line_total_snapshot} руб."
        )

    lines.append(f"Итого: {order.subtotal_snapshot} руб.")

    return "\n".join(lines)

def send_order_notification(chat_id: str, text: str) -> None:
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    if not token:
        raise ValueError("Telegram bot token is not configured.")
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Тело запроса в формате JSON
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, 
        data=data, 
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        response_data = json.load(response)
        if not response_data.get("ok"):
            raise RuntimeError(f"Failed to send Telegram message: {response_data}")
        
    