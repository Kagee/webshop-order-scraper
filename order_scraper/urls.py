from django.urls import path

from . import views
from .views_classbased import OrderListView

urlpatterns = [
    path("", views.index, name="index"),
    path("orders/", OrderListView.as_view(), name="order-list"),
]
