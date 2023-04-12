from django.contrib.contenttypes.fields import (
    GenericForeignKey,
    GenericRelation,
)
from django.contrib.contenttypes.models import ContentType
from django.db import models
from datetime import datetime

from .attachement import Attachement

# Create your models here.


class Order(models.Model):
    SHOPS_CHOICES = [
        ("adafruit", "Adafruit"),  # Only one that i have that is complete yet
    ]
    shop = models.CharField(
        max_length=30,
        choices=SHOPS_CHOICES,
    )
    # sub_shop can be "" since i.e. adafruit does
    # not have "subshops" like Amazon .de/.com/.co.jp
    shop_branch = models.CharField(
        max_length=50,
        default="",
        blank=True,
        help_text=(
            "The branch of the primary shop, i.e. DE or CO.JP"
            " for Amazon, or elfadistrelec.no for Distrelec."
        ),
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
