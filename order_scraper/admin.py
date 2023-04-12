from django.contrib import admin
from .models.order import Order
from .models.attachement import Attachement
from .models.orderitem import OrderItem

admin.site.register(Attachement)
admin.site.register(Order)
admin.site.register(OrderItem)
