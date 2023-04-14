from django.db import models
from django.utils.html import format_html
from django.contrib import admin


class Shop(models.Model):
    name = models.CharField(
        max_length=30,
        help_text="The name primary shop, Amazon, Distrelec or Adafruit",
    )
    branch_name = models.CharField(
        max_length=30,
        help_text=(
            "The branch of the primary shop, i.e. Amazon.de"
            " for Amazon, or elfadistrelec.no for Distrelec."
            " default is same as shop name"
        ),
        blank=True,
    )
    icon = models.ImageField(upload_to="shop/icons", blank=True)

    def longname(self):
        return f"{self.branch_name}" + (
            f", a branch of {self.name}"
            if self.name != self.branch_name
            else ""
        )

    @admin.display(description="Shop")
    def list_icon(self):
        return (
            format_html(
                f'<img src="{self.icon.url}" width="25"'
                f" />&nbsp;&nbsp;&nbsp; {self.longname()}"
            )
            if self.icon
            else f"{self.longname()}"
        )

    # @classmethod
    # def icon_img(cls, obj, size):
    #    return (
    #        format_html(f'<img src="{self.icon.url}" width="{size}" />')
    #        if self.icon
    #        else ""
    #    )

    order_url_template = models.CharField(
        max_length=250,
        help_text="The placeholder {order_id} can be used.",
        blank=True,
    )

    item_url_template = models.CharField(
        max_length=250,
        help_text="The placeholders {order_id} and {item_id} can be used.",
        blank=True,
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "branch_name"],
                name="unique_shop_name_branch_name",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.branch_name:
            self.branch_name = self.name
        super(Shop, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.branch_name}"
