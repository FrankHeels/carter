import re

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


def validate_hex_color(value: str) -> None:
    """Проверяет что значение является валидным HEX-цветом вида #RRGGBB."""
    if not re.match(r"^#[0-9A-Fa-f]{6}$", value):
        raise ValidationError(f"'{value}' — невалидный HEX-цвет. Используй формат #RRGGBB, например #1A1A1A")


def product_image_upload_path(instance: "ProductImage", filename: str) -> str:
    """Сохраняет фото в media/{slug категории}/{имя файла}."""
    category_slug = instance.product.category.slug
    return f"{category_slug}/{filename}"


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"

    def __str__(self) -> str:
        return self.name


class Size(models.Model):
    name = models.CharField(max_length=10)  # XS, S, M, L, XL, XXL
    order = models.PositiveSmallIntegerField(default=0)  # для сортировки XS→XXL

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return self.name


class Color(models.Model):
    name = models.CharField(max_length=50)       # "Черный"
    hex_code = models.CharField(max_length=7, validators=[validate_hex_color])  # "#1A1A1A"

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    care_instructions = models.TextField()
    price = models.IntegerField()
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="products",
    )
    slug = models.SlugField(unique=True)
    order = models.PositiveSmallIntegerField(default=0)  # ручная сортировка в каталоге
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "-created_at"]  # сначала по order, затем новые

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("product_detail", kwargs={"slug": self.slug})

    def get_available_sizes(self):
        """Возвращает размеры с наличием на складе."""
        return self.variants.select_related("size").order_by("size__order")

    def get_variants_grouped(self):
        """Возвращает варианты отсортированные по цвету и размеру — для группировки в шаблоне."""
        return self.variants.select_related("size", "color").order_by("color__name", "size__order")

    def get_main_image(self) -> "ProductImage | None":
        """Возвращает главное фото товара для отображения в каталоге."""
        return self.images.filter(is_main=True).first() or self.images.first()
    
    def get_main_image_for_color(self, color: Color):
        color_images = self.images.filter(color=color)
        return (
            color_images.filter(is_main=True).first()
            or color_images.first()
            or self.get_main_image()
        )
    
    def get_quarter_price(self) -> int:
        return self.price // 4


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",  # product.images.all()
    )
    image = models.ImageField(upload_to=product_image_upload_path)
    is_main = models.BooleanField(default=False)  # главное фото для каталога
    order = models.PositiveSmallIntegerField(default=0)  # порядок в галерее
    color = models.ForeignKey(
        Color,
        on_delete=models.SET_NULL,
        related_name="images",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return f"{self.product.name} — image #{self.order}"


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    size = models.ForeignKey(Size, on_delete=models.CASCADE)
    color = models.ForeignKey(Color, on_delete=models.CASCADE)
    stock = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # запрещает дубли: один и тот же товар+размер+цвет не может быть дважды
        unique_together = ("product", "size", "color")

    def __str__(self) -> str:
        return f"{self.product.name} / {self.color.name} / {self.size.name} — {self.stock} pcs"

    @property
    def is_available(self) -> bool:
        """Есть ли вариант в наличии."""
        return self.stock > 0

    @property
    def main_image(self):
        return self.product.get_main_image_for_color(self.color)
