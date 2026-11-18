from decimal import ROUND_HALF_UP, Decimal

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from products.models import Product

from . import services
from .forms import DiscountForm
from .models import Sale

CART_SESSION_KEY = "pos_cart"
DISCOUNT_TYPE_KEY = "pos_discount_type"
DISCOUNT_VALUE_KEY = "pos_discount_value"
MONEY_PLACES = Decimal("0.01")


def _get_cart(request):
    """Read the session cart as {int product id: int quantity}."""
    raw_cart = request.session.get(CART_SESSION_KEY, {})
    cart = {}
    for product_id, quantity in raw_cart.items():
        try:
            cart[int(product_id)] = int(quantity)
        except (TypeError, ValueError):
            continue
    return cart


def _save_cart(request, cart):
    """Store only product ids and quantities; prices are never kept in the session."""
    if cart:
        request.session[CART_SESSION_KEY] = {
            str(product_id): quantity for product_id, quantity in cart.items()
        }
    else:
        request.session.pop(CART_SESSION_KEY, None)


def _get_discount(request):
    """Return the session discount type and raw value, falling back to no discount."""
    discount_type = request.session.get(DISCOUNT_TYPE_KEY, Sale.DiscountType.NONE)
    if discount_type not in Sale.DiscountType.values:
        discount_type = Sale.DiscountType.NONE
    return discount_type, request.session.get(DISCOUNT_VALUE_KEY, "")


def _cart_rows(cart):
    """Build display rows and subtotal from the current database prices."""
    rows = []
    subtotal = Decimal("0.00")
    products = Product.objects.filter(pk__in=cart).order_by("name")
    for product in products:
        quantity = cart[product.pk]
        line_total = (product.price * quantity).quantize(
            MONEY_PLACES, rounding=ROUND_HALF_UP
        )
        subtotal += line_total
        rows.append(
            {
                "product": product,
                "quantity": quantity,
                "line_total": line_total,
            }
        )
    return rows, subtotal


def _search_results(query, cart):
    """Return up to 10 active products matching name/SKU or an exact barcode."""
    if not query:
        return []
    products = (
        Product.objects.filter(is_active=True)
        .filter(
            Q(name__icontains=query)
            | Q(sku__icontains=query)
            | Q(barcode=query)
        )
        .order_by("name")[:10]
    )
    return [
        {"product": product, "in_cart": cart.get(product.pk, 0)}
        for product in products
    ]


def _form_error(form):
    """Return the first validation error so it can be shown as a message."""
    for errors in form.errors.values():
        if errors:
            return errors[0]
    return "Please check the form."


def _pos_redirect(request):
    """Redirect back to the POS screen while preserving the search term."""
    target = reverse("sales:pos")
    query = request.POST.get("q", "").strip()
    if query:
        target = f"{target}?{urlencode({'q': query})}"
    return redirect(target)


def pos(request):
    cart = _get_cart(request)
    rows, subtotal = _cart_rows(cart)
    discount_type, discount_value = _get_discount(request)
    discount_amount = Decimal("0.00")
    discount_error = ""

    if rows:
        try:
            discount_amount = services.calculate_discount(
                subtotal, discount_type, discount_value or Decimal("0")
            )
        except services.CheckoutError as exc:
            discount_error = str(exc)

    query = request.GET.get("q", "").strip()
    return render(
        request,
        "sales/pos.html",
        {
            "query": query,
            "search_results": _search_results(query, cart),
            "rows": rows,
            "subtotal": subtotal,
            "discount_form": DiscountForm(
                initial={
                    "discount_type": discount_type,
                    "discount_value": discount_value,
                }
            ),
            "discount_amount": discount_amount,
            "discount_error": discount_error,
            "total": subtotal - discount_amount,
        },
    )


@require_POST
def pos_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    if not product.is_active:
        messages.error(request, f'"{product.name}" is not available for sale.')
        return _pos_redirect(request)

    cart = _get_cart(request)
    in_cart = cart.get(product.pk, 0)
    if product.stock_quantity < 1:
        messages.error(request, f'"{product.name}" is out of stock.')
    elif in_cart >= product.stock_quantity:
        messages.error(
            request,
            f'Only {product.stock_quantity} unit(s) of "{product.name}" in stock.',
        )
    else:
        cart[product.pk] = in_cart + 1
        _save_cart(request, cart)
        messages.success(request, f'Added "{product.name}" to the cart.')
    return _pos_redirect(request)


@require_POST
def pos_update(request, product_id):
    cart = _get_cart(request)
    if product_id not in cart:
        messages.error(request, "That product is not in the cart.")
        return _pos_redirect(request)

    product = Product.objects.filter(pk=product_id).first()
    if product is None or not product.is_active:
        cart.pop(product_id, None)
        _save_cart(request, cart)
        messages.error(request, "That product is no longer available and was removed.")
        return _pos_redirect(request)

    try:
        quantity = int(request.POST.get("quantity", ""))
    except (TypeError, ValueError):
        messages.error(request, "Quantity must be a whole number.")
        return _pos_redirect(request)

    if quantity < 1:
        messages.error(request, "Quantity must be at least 1.")
    elif quantity > product.stock_quantity:
        messages.error(
            request,
            f'Only {product.stock_quantity} unit(s) of "{product.name}" in stock.',
        )
    else:
        cart[product_id] = quantity
        _save_cart(request, cart)
        messages.success(request, f'Quantity for "{product.name}" updated.')
    return _pos_redirect(request)


@require_POST
def pos_remove(request, product_id):
    cart = _get_cart(request)
    if cart.pop(product_id, None) is not None:
        _save_cart(request, cart)
        name = (
            Product.objects.filter(pk=product_id)
            .values_list("name", flat=True)
            .first()
            or "Product"
        )
        messages.success(request, f'"{name}" removed from the cart.')
    else:
        messages.error(request, "That product is not in the cart.")
    return _pos_redirect(request)


@require_POST
def pos_discount(request):
    form = DiscountForm(request.POST)
    if not form.is_valid():
        messages.error(request, _form_error(form))
        return _pos_redirect(request)

    cart = _get_cart(request)
    _rows, subtotal = _cart_rows(cart)
    try:
        services.calculate_discount(
            subtotal,
            form.cleaned_data["discount_type"],
            form.cleaned_data["discount_value"],
        )
    except services.CheckoutError as exc:
        messages.error(request, str(exc))
        return _pos_redirect(request)

    request.session[DISCOUNT_TYPE_KEY] = form.cleaned_data["discount_type"]
    request.session[DISCOUNT_VALUE_KEY] = str(
        form.cleaned_data["discount_value"].quantize(
            MONEY_PLACES, rounding=ROUND_HALF_UP
        )
    )
    messages.success(request, "Discount applied.")
    return _pos_redirect(request)


@require_POST
def pos_checkout(request):
    cart = _get_cart(request)
    if not cart:
        messages.error(request, "The cart is empty.")
        return _pos_redirect(request)

    form = DiscountForm(request.POST)
    if not form.is_valid():
        messages.error(request, _form_error(form))
        return _pos_redirect(request)

    try:
        sale = services.checkout(
            list(cart.items()),
            form.cleaned_data["discount_type"],
            form.cleaned_data["discount_value"],
            request.user,
        )
    except services.CheckoutError as exc:
        messages.error(request, str(exc))
        return _pos_redirect(request)

    _save_cart(request, {})
    request.session.pop(DISCOUNT_TYPE_KEY, None)
    request.session.pop(DISCOUNT_VALUE_KEY, None)
    messages.success(request, f"Sale {sale.invoice_number} completed.")
    return redirect("sales:sale_detail", pk=sale.pk)


def sale_detail(request, pk):
    sale = get_object_or_404(
        Sale.objects.select_related("created_by").prefetch_related("items"), pk=pk
    )
    return render(request, "sales/sale_detail.html", {"sale": sale})
