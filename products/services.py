from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Category, Product, StockAdjustment

MONEY_PLACES = Decimal("0.01")


def _quantize_price(price):
    return Decimal(price).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


@transaction.atomic
def adjust_stock(product, change, reason, *, reference="", note="", created_by=None):
    """Change stock only here: lock the product and write a StockAdjustment in the same transaction."""
    if not isinstance(change, int) or isinstance(change, bool) or change == 0:
        raise ValidationError("Stock change must be a non-zero whole number.")
    if reason not in StockAdjustment.Reason.values:
        raise ValidationError("Unknown stock adjustment reason.")

    locked = Product.objects.select_for_update().get(pk=product.pk)
    new_stock = locked.stock_quantity + change
    if new_stock < 0:
        raise ValidationError("Stock cannot go below zero.")

    locked.stock_quantity = new_stock
    locked.save(update_fields=["stock_quantity", "updated_at"])
    return StockAdjustment.objects.create(
        product=locked,
        change=change,
        stock_after=new_stock,
        reason=reason,
        reference=reference,
        note=note,
        created_by=created_by,
    )


@transaction.atomic
def create_product(
    *, name, sku, category, barcode, price, stock_quantity, created_by=None
):
    """Create a product at zero stock, then record opening stock as an INITIAL adjustment."""
    product = Product.objects.create(
        name=name,
        sku=sku,
        category=category,
        barcode=barcode,
        price=_quantize_price(price),
        stock_quantity=0,
    )
    if stock_quantity > 0:
        adjust_stock(
            product,
            stock_quantity,
            StockAdjustment.Reason.INITIAL,
            note="Initial stock on product creation",
            created_by=created_by,
        )
    return product


def update_product(product, *, name, sku, category, barcode, price):
    """Update editable product details; stock and active state are never changed here."""
    product.name = name
    product.sku = sku
    product.category = category
    product.barcode = barcode
    product.price = _quantize_price(price)
    product.save(
        update_fields=["name", "sku", "category", "barcode", "price", "updated_at"]
    )
    return product


def deactivate_product(product):
    """Soft-delete a product by marking it inactive; product rows are never removed."""
    if product.is_active:
        product.is_active = False
        product.save(update_fields=["is_active", "updated_at"])
    return product


def create_category(name):
    """Create a product category from a validated, unique name."""
    return Category.objects.create(name=name)
