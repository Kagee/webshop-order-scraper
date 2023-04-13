from django.contrib import admin

from .models.attachement import Attachement
from .models.order import Order
from .models.orderitem import OrderItem
from .models.shop import Shop

admin.site.register(Attachement)
admin.site.register(OrderItem)


class OrderAdmin(admin.ModelAdmin):
    readonly_fields = [
        "shop",
        "date",
        "order_url",
        "indent_extra_data",
    ]


admin.site.register(Order, OrderAdmin)


class ShopAdmin(admin.ModelAdmin):
    list_display = [lambda obj: obj.longname()]
    readonly_fields = [
        "id",
    ]

    def get_form(self, request, obj=None, **kwargs):
        form = super(ShopAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields["order_url_template"].widget.attrs[
            "style"
        ] = "width: 45em;"
        form.base_fields["item_url_template"].widget.attrs[
            "style"
        ] = "width: 45em;"
        return form


admin.site.register(Shop, ShopAdmin)
