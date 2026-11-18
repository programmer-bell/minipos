from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Category, Product, StockAdjustment

MONEY_PLACES = Decimal("0.01")


def _quantize_price(price):
    return Decimal(price).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


@transaction.atomic
def adjust_stock(product_id, change, reason, user=None, reference="", note=""):
    """Change stock only here: lock the product and write a StockAdjustment in the same transaction."""
    if not isinstance(change, int) or isinstance(change, bool) or change == 0:
        raise ValidationError("Stock change must be a non-zero whole number.")
    if reason not in StockAdjustment.Reason.values:
        raise ValidationError("Unknown stock adjustment reason.")

    product = Product.objects.select_for_update().get(pk=product_id)
    new_stock = product.stock_quantity + change
    if new_stock < 0:
        raise ValidationError(
            f"Only {product.stock_quantity} unit(s) in stock; "
            f"cannot remove {abs(change)}."
        )

    product.stock_quantity = new_stock
    product.save(update_fields=["stock_quantity", "updated_at"])
    return StockAdjustment.objects.create(
        product=product,
        change=change,
        stock_after=new_stock,
        reason=reason,
        reference=reference,
        note=note,
        created_by=user,
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
            product.pk,
            stock_quantity,
            StockAdjustment.Reason.INITIAL,
            user=created_by,
            note="Initial stock on product creation",
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
