from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from products.models import Product
from sales.models import Sale

MONEY_PLACES = Decimal("0.01")


def get_dashboard_data():
    """Return today's sales summary, active products, low stock and recent sales.

    Today uses the local timezone day boundary, and totals are aggregated in the
    database so no sales rows are loaded into Python.
    """
    today = timezone.localdate()
    start = timezone.make_aware(
        datetime.combine(today, time.min), timezone.get_current_timezone()
    )
    end = start + timedelta(days=1)

    sales_today = Sale.objects.filter(
        created_at__gte=start, created_at__lt=end
    ).aggregate(total=Sum("total"), count=Count("pk"))
    today_sales_total = (sales_today["total"] or Decimal("0.00")).quantize(
        MONEY_PLACES, rounding=ROUND_HALF_UP
    )

    return {
        "today_sales_total": today_sales_total,
        "today_sales_count": sales_today["count"],
        "active_product_count": Product.objects.filter(is_active=True).count(),
        "low_stock_products": Product.objects.filter(
            is_active=True, stock_quantity__lt=5
        ).order_by("stock_quantity", "name"),
        "recent_sales": Sale.objects.order_by("-created_at", "-id")[:5],
    }
