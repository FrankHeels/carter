from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class CreatePaymentData:
    order_id: int
    amount: Decimal
    currency: str
    description: str
    return_url: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class CreatedPayment:
    provider_payment_id: str
    status: str
    confirmation_url: str | None
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class PaymentNotification:
    provider_payment_id: str
    status: str
    event: str
    raw_data: dict[str, Any]
