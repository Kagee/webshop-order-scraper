from django.contrib.contenttypes.fields import (GenericForeignKey,
                                                GenericRelation)
from django.contrib.contenttypes.models import ContentType
from django.db import models

# Create your models here.

class Attachement(models.Model):
    ATTACHEMENT_TYPE_CHOICES = [
        ("datasheet", "Datasheet"),
        ("item_pdf", "Item PDF"),
        ("item_pdf", "Item HTML"),
        ("item_thumnail", "Thumbnail"),
        ("other", "Other"),
        ("unknown", "Unknown"),
    ]
    ATTACHEMENT_FILETYPE_CHOICES = [
        ("pdf", "PDF"),
        ("jpg", "JPG"),
        ("png", "PNG"),
        ("txt", "Plain text"),
        ("html", "HTML"),
        ("other", "Other"),
        ("unknown", "Unknown"),
    ]
    name = models.CharField(max_length=50)
    type = models.CharField(max_length=50, choices=ATTACHEMENT_TYPE_CHOICES)
    url = models.CharField(max_length=50)
    file = models.CharField(max_length=50)
    filetype = models.CharField(max_length=50, choices=ATTACHEMENT_FILETYPE_CHOICES)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

class Order(models.Model):
    SHOPS_CHOICES = [
        ("adafruit", "Adafruit"),
    ]
    shop = models.CharField(max_length=20, choices=SHOPS_CHOICES,)
    # sub_shop can be blank since i.e. adafruit does
    # not have "subshops" like Amazon .de/.com/.co.jp
    sub_shop = models.CharField(max_length=50, blank=True)
    date = models.DateTimeField("order date")
    attachements = GenericRelation(Attachement)
    created_at = models.DateTimeField(auto_now_add=True)

class OrderItems(models.Model):
    name = models.CharField(max_length=250)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    attachements = GenericRelation(Attachement)
