from datetime import datetime

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from . import Attachement, Shop

# Create your models here.


class Order(models.Model):
    shop = models.ForeignKey(
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
    )

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(
                fields=["shop", "shop_branch", "order_id"],
                name="unique_shop_branch_order_id",
            )
        ]

    date: datetime = models.DateTimeField("order date")
    attachements = GenericRelation(Attachement)
    created_at = models.DateTimeField(auto_now_add=True)
    # Extra data that we do not import into model
    extra_data = models.JSONField(
        default=dict,
        blank=True,
    )

    def __shopname__(self):
        return (
            f"{self.shop}{ '' if not self.shop_branch else f' ({self.shop_branch})' }"
        )

    def __str__(self):
        return (
            f"{self.__shopname__()} #{self.order_id} placed at"
            f" {self.date.strftime('%Y-%m-%d') } with"
            f" {self.items.count()} items"
        )
