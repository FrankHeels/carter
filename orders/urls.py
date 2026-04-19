from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("success/", views.success, name="success"),
    path("checkout/", views.checkout, name="checkout"),
    # path("orders/<int:pk>/", views.OrderDetailView.as_view(), name="order-detail"),
    # path("orders/create/", views.OrderCreateView.as_view(), name="order-create"),
]
