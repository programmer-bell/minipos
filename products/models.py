from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    barcode = models.CharField(max_length=64, blank=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["name"])]
        constraints = [
            models.UniqueConstraint(
                fields=["barcode"],
                condition=~Q(barcode=""),
                name="unique_nonblank_barcode",
            ),
            models.CheckConstraint(
                condition=Q(price__gte=0), name="product_price_gte_0"
            ),
        ]

    def save(self, *args, **kwargs):
        self.sku = self.sku.strip().upper()  # "abc-1" and "ABC-1" are the same SKU
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.sku})"


class StockAdjustment(models.Model):
    class Reason(models.TextChoices):
        INITIAL = "initial", "Initial stock"
        RESTOCK = "restock", "Restock"
        CORRECTION = "correction", "Manual correction"
        SALE = "sale", "Sale"

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="adjustments"
    )
    change = models.IntegerField()  # signed: +10 restock, -2 sale
    stock_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=20, choices=Reason.choices)
    reference = models.CharField(max_length=30, blank=True)  # e.g. invoice number
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=~Q(change=0), name="adjustment_change_not_zero"),
        ]