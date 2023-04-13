from datetime import datetime

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from .attachement import Attachement
from .shop import Shop


class Order(models.Model):
    readonly_fields = ["order_id", "date"]

    shop: Shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="orders",
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

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(
                fields=["shop", "order_id"],
                name="unique_shop_branch_order_id",
            )
        ]

    date: datetime = models.DateTimeField(
        "order date",
        editable=False,
    )
    attachements = GenericRelation(Attachement)
    created_at = models.DateTimeField(auto_now_add=True)
    # Extra data that we do not import into model
    extra_data = models.JSONField(
        default=dict,
        blank=True,
    )

    def __str__(self):
        return (
            f"{self.shop.branch_name} #{self.order_id} placed at"
            f" {self.date.strftime('%Y-%m-%d') } with"
            f" {self.items.count()} items"
        )
