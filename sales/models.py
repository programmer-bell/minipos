from django.conf import settings
from django.db import models
from django.db.models import F, Q

from products.models import Product


class Sale(models.Model):
    class DiscountType(models.TextChoices):
        NONE = "none", "No discount"
        FLAT = "flat", "Flat amount"
        PERCENT = "percent", "Percentage"

    invoice_number = models.CharField(max_length=20, unique=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount_type = models.CharField(
        max_length=10, choices=DiscountType.choices, default=DiscountType.NONE
    )
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(discount_amount__lte=F("subtotal")),
                name="sale_discount_lte_subtotal",
            ),
            models.CheckConstraint(
                condition=Q(total__gte=0), name="sale_total_gte_0"
            ),
        ]

    def __str__(self):
        return self.invoice_number


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="sale_items")
    # Snapshots: what the product looked like at the moment of sale
    product_name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="saleitem_quantity_gt_0"),
            models.UniqueConstraint(fields=["sale", "product"], name="unique_product_per_sale"),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"