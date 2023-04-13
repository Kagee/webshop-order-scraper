from django.db import models


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
        default=name,
    )
    # https://www.adafruit.com/index.php?main_page=account_history_info&order_id={order_id}
    order_url_template = models.CharField(
        max_length=250,
        help_text="The placeholder {order_id} can be used.",
        blank=True,
    )
    # https://www.adafruit.com/product/{item_id}
    item_url_template = models.CharField(
        max_length=250,
        help_text="The placeholders {order_id} and {item_id} can be used.",
        blank=True,
    )
