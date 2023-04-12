from django.views import View
from django.views.generic.list import ListView

from django.http import HttpResponse
from .models import Order


class OrderListView(ListView):
    model = Order
    # def get(self, request):
    #    # <view logic>
    # return HttpResponse("result")
