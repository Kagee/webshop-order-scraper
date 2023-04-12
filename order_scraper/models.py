from django.contrib.contenttypes.fields import (
    GenericForeignKey,
    GenericRelation,
)
from django.contrib.contenttypes.models import ContentType
from django.db import models

# Create your models here.


class Attachement(models.Model):
    ATTACHEMENT_TYPE_CHOICES = [
        ("datasheet", "Datasheet"),
        ("item_pdf", "Scraped Item PDF"),
        ("item_pdf", "Scraped Item HTML"),
        ("item_thumnail", "Thumbnail"),
        ("other", "Other"),
        ("unknown", "Unknown"),
    ]
    name = models.CharField(max_length=50)
    type = models.CharField(max_length=50, choices=ATTACHEMENT_TYPE_CHOICES)
    url = models.CharField(max_length=50)
    # https://docs.djangoproject.com/en/3.2/ref/models/fields/#filefield
    file = models.FileField(upload_to="", storage=None)
    # Detected mimetype?
    filetype = models.CharField(max_length=50, blank=True)
    # GenericForeignKey so Attachement can be used by "any" model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()


class Order(models.Model):
    SHOPS_CHOICES = [
        ("adafruit", "Adafruit"),  # Only one that i have that is complete yet
    ]
    shop = models.CharField(
        max_length=20,
        choices=SHOPS_CHOICES,
    )
    # sub_shop can be blank since i.e. adafruit does
    # not have "subshops" like Amazon .de/.com/.co.jp
    shop_branch = models.CharField(
        max_length=50,
        default="",
        help_text=(
            "The branch of the primary shop, i.e. DE or CO.JP for Amazon, or"
            " elfadistrelec.no for Distrelec."
        ),
    )
    date = models.DateTimeField("order date")
    attachements = GenericRelation(Attachement)
    created_at = models.DateTimeField(auto_now_add=True)


class OrderItems(models.Model):
    name = models.CharField(max_length=250)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    attachements = GenericRelation(Attachement)
