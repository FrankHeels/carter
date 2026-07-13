# payments/gateways/yookassa.py

from yookassa import Configuration, Payment as YooKassaPayment

from payments.dto import (
    CreatePaymentData,
    CreatedPayment,
    PaymentNotification,
)


class YooKassaGateway:
    def __init__(self, shop_id: str, secret_key: str):
        Configuration.account_id = shop_id
        Configuration.secret_key = secret_key

    def create_payment(self, data: CreatePaymentData) -> CreatedPayment:
        response = YooKassaPayment.create({
            "amount": {
                "value": str(data.amount),
                "currency": data.currency,
            },
            "confirmation": {
                "type": "redirect",
                "return_url": data.return_url,
            },
            "capture": True,
            "description": data.description,
            "metadata": data.metadata,
        })

        raw = response.json()

        return CreatedPayment(
            provider_payment_id=str(response.id),
            status=response.status,
            confirmation_url=response.confirmation.confirmation_ur,
            raw_response=raw,
        )

    def parse_notification(self, payload: dict) -> PaymentNotification:
        payment_object = payload["object"]

        return PaymentNotification(
            provider_payment_id=payment_object["id"],
            status=payment_object["status"],
            event=payload["event"],
            raw_data=payload,
        )

    def get_payment_status(self, provider_payment_id: str) -> str:
        response = YooKassaPayment.find_one(provider_payment_id)
        return response.status
