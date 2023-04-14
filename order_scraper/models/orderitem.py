from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from .attachement import Attachement
from .order import Order


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
    )
    count = models.PositiveIntegerField("number of items")
    order: Order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    attachements = GenericRelation(Attachement)
    thumbnail = models.ForeignKey(
        Attachement, on_delete=models.CASCADE, blank=True, null=True
    )
    url = models.URLField("url", blank=True)
    # Extra data that we do not import into model
    extra_data = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return (
            f"{self.order.shop.branch_name} item #{self.item_id}: {self.name}"
        )
