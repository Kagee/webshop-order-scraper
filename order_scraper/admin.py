from django.contrib import admin
from django.utils.html import format_html

from .models.attachement import Attachement
from .models.order import Order
from .models.orderitem import OrderItem
from .models.shop import Shop

admin.site.register(Attachement)
admin.site.register(OrderItem)


class OrderAdmin(admin.ModelAdmin):
    readonly_fields = [
        lambda obj: obj.shop.list_icon(),
        "date",
        "order_url",
        "items_list",
        "indent_extra_data",
    ]
    list_display = ["admin_list_render"]


admin.site.register(Order, OrderAdmin)


class ShopAdmin(admin.ModelAdmin):
    list_display = ["list_icon", "id"]
    readonly_fields = ["id", "change_icon"]
    fields = [
        "id",
        "name",
        "branch_name",
        "icon",
        "change_icon",
        "order_url_template",
        "item_url_template",
    ]

    @admin.display(description="Icon preview")
    def change_icon(self, instance):
        return (
            format_html(f'<img src="{instance.icon.url}" width="75" />')
            if instance.icon
            else ""
        )

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
