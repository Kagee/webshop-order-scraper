from django.contrib import admin
from django.db import models
from django.forms import Textarea, TextInput

from .models.attachement import Attachement
from .models.order import Order
from .models.orderitem import OrderItem
from .models.shop import Shop

admin.site.register(Attachement)
admin.site.register(Order)
admin.site.register(OrderItem)


class ShopAdmin(admin.ModelAdmin):
    # formfield_overrides = {
    #    models.CharField: {"widget": TextInput(attrs={"size": "75"})},
    # }
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
