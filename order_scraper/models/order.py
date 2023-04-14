import pprint
from datetime import datetime

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils.html import escape, format_html

from .attachement import Attachement
from .shop import Shop


class Order(models.Model):
    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(
                fields=["shop", "order_id"],
                name="unique_shop_order_id",
            )
        ]

    shop: Shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="orders",
        editable=False,
    )

    order_id = models.CharField(
        "the original shop order id",
        max_length=100,
        default="",
        help_text=(
            "The original order id from the shop. Not to be "
            "cofused with the internal database id."
        ),
        blank=False,
        editable=False,
    )

    date: datetime = models.DateField(
        "order date",
        editable=False,
    )
    attachements = GenericRelation(Attachement)
    created_at = models.DateTimeField(auto_now_add=True)
    # Extra data that we do not import into model
    extra_data = models.JSONField(
        default=dict,
        blank=True,
        editable=False,
    )

    def order_url(self):
        return format_html(
            '{} (<a href="{}" target="_blank">Open order on {}</a>)',
            self.order_id,
            self.shop.order_url_template.format(order_id=self.order_id),
                        self.shop.branch_name
        )

    order_url.short_description = "Order ID"

    def indent_extra_data(self):
        return format_html(
            "<pre>{}</pre>",
            escape(pprint.PrettyPrinter(indent=2).pformat(self.extra_data)),
        )

    indent_extra_data.short_description = "Extra data"

    def __str__(self):
        return (
            f"{self.shop.branch_name} order #{self.order_id} with"
            # 2pylint: disable=no-member
            f" {self.items.count()} items"
        )
