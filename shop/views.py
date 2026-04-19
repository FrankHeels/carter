from django.views.generic import ListView, DetailView

from .models import Product


class ProductListView(ListView):
    model = Product
    template_name = "shop/index.html"
    context_object_name = "products"

    def get_queryset(self):
        # prefetch images чтобы не делать лишних запросов в шаблоне
        return Product.objects.prefetch_related("images").all()


class ProductDetailView(DetailView):
    model = Product
    template_name = "shop/product_detail.html"
    context_object_name = "product"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        # подгружаем варианты с размерами и цветами, и изображения — одним запросом
        return Product.objects.prefetch_related(
            "images",
            "variants__size",
            "variants__color",
        )
