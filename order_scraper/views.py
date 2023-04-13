from django.views.generic.list import ListView

from .models.order import Order


class OrderListView(ListView):
    model = Order
    paginate_by = 2
