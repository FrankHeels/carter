from django import forms

from .models import Order

class GuestCheckForm(forms.ModelForm):
    FIELD_CONFIG = {
        "customer_name": {
            "label": "Имя и фамилия",
            "placeholder": "Как к вам обращаться",
            "autocomplete": "name",
        },
        "customer_email": {
            "label": "Email",
            "placeholder": "name@example.com",
            "autocomplete": "email",
        },
        "customer_phone": {
            "label": "Телефон",
            "placeholder": "+7 999 000-00-00",
            "autocomplete": "tel",
        },
        "delivery_city": {
            "label": "Город",
            "placeholder": "Москва",
            "autocomplete": "address-level2",
        },
        "delivery_street": {
            "label": "Улица",
            "placeholder": "Тверская",
            "autocomplete": "address-line1",
        },
        "delivery_house": {
            "label": "Дом",
            "placeholder": "10",
            "autocomplete": "address-line1",
        },
        "delivery_apartment": {
            "label": "Квартира / офис (необязательно)",
            "placeholder": "15",
            "autocomplete": "address-line2",
        },
        "delivery_postal_code": {
            "label": "Почтовый индекс",
            "placeholder": "123456",
            "autocomplete": "postal-code",
        },
        "delivery_comment": {
            "label": "Комментарий к доставке (необязательно)",
            "placeholder": "Например, код домофона или удобное время звонка",
            "autocomplete": "off",
        },
    }

    class Meta:
        model = Order
        fields = [
            "customer_name",
            "customer_email",
            "customer_phone",
            "delivery_city",
            "delivery_street",
            "delivery_house",
            "delivery_apartment",
            "delivery_postal_code",
            "delivery_comment",
        ]
        widgets = {
            "delivery_comment": forms.Textarea(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        input_classes = (
            "mt-3 w-full border border-zinc-800 bg-zinc-950 px-5 py-4 text-sm text-white "
            "outline-none transition-colors placeholder:text-zinc-600 focus:border-white"
        )
        textarea_classes = (
            "mt-3 min-h-32 w-full resize-y border border-zinc-800 bg-zinc-950 px-5 py-4 text-sm text-white "
            "outline-none transition-colors placeholder:text-zinc-600 focus:border-white"
        )

        for field_name, field in self.fields.items():
            config = self.FIELD_CONFIG[field_name]
            field.label = config["label"]
            field.error_messages["required"] = "Заполните это поле."

            widget_classes = textarea_classes if field_name == "delivery_comment" else input_classes
            field.widget.attrs.update(
                {
                    "class": widget_classes,
                    "placeholder": config["placeholder"],
                    "autocomplete": config["autocomplete"],
                }
            )

        self.fields["delivery_comment"].widget.attrs["rows"] = 4
