import base64
import pprint
from pathlib import Path

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils.html import escape, format_html

from .attachement import Attachement
from .order import Order


def thumnail_path(instance, filename):
    ext = Path(filename).suffix[1:]
    filename_str = f"{instance.order.id}-{instance.item_id}-{ instance.item_sku if instance.item_sku else '' }"
    filename_b64 = base64.urlsafe_b64encode(filename_str).decode("utf-8")
    return f"items/thumbnails/{filename_b64}.{ext}"


class OrderItem(models.Model):
    name = models.CharField(max_length=200)
    item_id = models.CharField(
        "the original shop item id",
        max_length=100,
        default="",
        help_text=(
            "The original item id from the shop. Not to be "
            "cofused with the internal database id."
        ),
        blank=False,
    )
    item_sku = models.CharField(
        "the original shop item sku",
        max_length=100,
        default="",
        help_text=(
            "The original item sku."
        ),
        blank=True,
    )
    count = models.PositiveIntegerField("number of items", default=1)
    order: Order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    attachements = GenericRelation(Attachement)
    thumbnail = models.ImageField(upload_to=thumnail_path, blank=True)

    def item_url(self):
        return format_html(
            '{} (<a href="{}" target="_blank">Open item page on {}}</a>)',
            self.order_id,
            self.shop.order_url_template.format(order_id=self.order_id),
            self.shop.branch_name
        )

    item_url.short_description = "Order ID"

    # Extra data that we do not import into model
    extra_data = models.JSONField(default=dict, blank=True)

    def indent_extra_data(self):
        return format_html(
            "<pre>{}</pre>",
            escape(pprint.PrettyPrinter(indent=2).pformat(self.extra_data)),
        )

    indent_extra_data.short_description = "Extra data"


    def __str__(self):
        return (
            f"{self.order.shop.branch_name} item #{self.item_id}: {self.name}"
        )
