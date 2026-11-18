from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from products.models import Product, StockAdjustment
from products.services import adjust_stock

from .models import Sale, SaleItem

MONEY_PLACES = Decimal("0.01")


class CheckoutError(Exception):
    """A checkout problem with a message that can be shown to the user."""


def _to_money(value):
    """Convert a value to a 2-place Decimal with ROUND_HALF_UP rounding."""
    try:
        return Decimal(str(value)).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise CheckoutError("Amount must be a number.")


def calculate_discount(subtotal, discount_type, discount_value):
    """Return a 2-place discount that is never negative and never above the subtotal.

    FLAT values must fit inside the subtotal and PERCENT values must be 0-100.
    """
    if discount_type not in Sale.DiscountType.values:
        raise CheckoutError("Unknown discount type.")

    subtotal = _to_money(subtotal)
    if discount_type == Sale.DiscountType.NONE:
        return Decimal("0.00")

    value = _to_money(discount_value)
    if value < 0:
        raise CheckoutError("Discount value cannot be negative.")

    if discount_type == Sale.DiscountType.FLAT:
        if value > subtotal:
            raise CheckoutError("Discount cannot be more than the subtotal.")
        amount = value
    else:
        if value > Decimal("100"):
            raise CheckoutError("Percentage discount cannot be more than 100.")
        amount = (subtotal * value / Decimal("100")).quantize(
            MONEY_PLACES, rounding=ROUND_HALF_UP
        )

    return min(amount, subtotal)


@transaction.atomic
def checkout(items, discount_type, discount_value, user):
    """Sell a cart atomically using prices and stock from locked database rows only.

    Duplicate products are merged, inactive or missing products are rejected, and
    stock is reduced through products.services.adjust_stock() with reason SALE.
    """
    quantities = {}
    for product_id, quantity in items:
        if not isinstance(product_id, int) or isinstance(product_id, bool):
            raise CheckoutError("The cart contains an invalid product.")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise CheckoutError("Quantity must be a whole number of at least 1.")
        quantities[product_id] = quantities.get(product_id, 0) + quantity

    if not quantities:
        raise CheckoutError("The cart is empty.")

    # Lock rows in id order so concurrent checkouts cannot deadlock each other.
    products = {
        product.pk: product
        for product in Product.objects.select_for_update()
        .filter(pk__in=quantities)
        .order_by("id")
    }

    missing = sorted(set(quantities) - set(products))
    if missing:
        ids = ", ".join(str(product_id) for product_id in missing)
        raise CheckoutError(f"Product no longer exists: {ids}.")

    inactive = [product.name for product in products.values() if not product.is_active]
    if inactive:
        names = ", ".join(f'"{name}"' for name in inactive)
        raise CheckoutError(f"Not available for sale: {names}.")

    shortages = [
        f'"{products[product_id].name}" has only '
        f"{products[product_id].stock_quantity} unit(s) in stock "
        f"(requested {quantity})."
        for product_id, quantity in quantities.items()
        if quantity > products[product_id].stock_quantity
    ]
    if shortages:
        raise CheckoutError(" ".join(shortages))

    subtotal = Decimal("0.00")
    line_items = []
    for product_id in sorted(quantities):
        product = products[product_id]
        quantity = quantities[product_id]
        unit_price = _to_money(product.price)
        line_total = (unit_price * quantity).quantize(
            MONEY_PLACES, rounding=ROUND_HALF_UP
        )
        line_items.append((product, quantity, unit_price, line_total))
        subtotal += line_total

    discount_amount = calculate_discount(subtotal, discount_type, discount_value)
    total = subtotal - discount_amount
    stored_discount_value = (
        Decimal("0.00")
        if discount_type == Sale.DiscountType.NONE
        else _to_money(discount_value)
    )

    sale = Sale.objects.create(
        # A temporary unique number satisfies the unique column until the pk exists.
        invoice_number=f"TMP-{uuid4().hex[:16]}",
        subtotal=subtotal,
        discount_type=discount_type,
        discount_value=stored_discount_value,
        discount_amount=discount_amount,
        total=total,
        created_by=user,
    )
    sale.invoice_number = f"INV-{timezone.localdate():%Y%m%d}-{sale.pk:05d}"
    sale.save(update_fields=["invoice_number"])

    for product, quantity, unit_price, line_total in line_items:
        SaleItem.objects.create(
            sale=sale,
            product=product,
            product_name=product.name,
            sku=product.sku,
            unit_price=unit_price,
            quantity=quantity,
            line_total=line_total,
        )

    for product, quantity, _unit_price, _line_total in line_items:
        adjust_stock(
            product.pk,
            -quantity,
            StockAdjustment.Reason.SALE,
            user=user,
            reference=sale.invoice_number,
        )

    return sale
