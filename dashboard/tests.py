from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard import services
from products.models import Category, Product
from sales.models import Sale


class DashboardServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="dashboard-user", password="test-password-123"
        )
        category = Category.objects.create(name="Groceries")
        cls.stock_ten = Product.objects.create(
            name="Stock Ten",
            sku="STK-010",
            category=category,
            barcode="",
            price=Decimal("10.00"),
            stock_quantity=10,
        )
        cls.stock_five = Product.objects.create(
            name="Stock Five",
            sku="STK-005",
            category=category,
            barcode="",
            price=Decimal("10.00"),
            stock_quantity=5,
        )
        cls.stock_four = Product.objects.create(
            name="Stock Four",
            sku="STK-004",
            category=category,
            barcode="",
            price=Decimal("10.00"),
            stock_quantity=4,
        )
        cls.stock_zero = Product.objects.create(
            name="Stock Zero",
            sku="STK-000",
            category=category,
            barcode="",
            price=Decimal("10.00"),
            stock_quantity=0,
        )
        cls.inactive = Product.objects.create(
            name="Inactive Product",
            sku="INA-001",
            category=category,
            barcode="",
            price=Decimal("10.00"),
            stock_quantity=1,
            is_active=False,
        )

    def local_day_start(self):
        today = timezone.localdate()
        return timezone.make_aware(
            datetime.combine(today, time.min), timezone.get_current_timezone()
        )

    def make_sale(self, total, created_at=None):
        sale = Sale.objects.create(
            invoice_number=f"INV-TEST-{Sale.objects.count() + 1:05d}",
            subtotal=total,
            total=total,
            created_by=self.user,
        )
        if created_at is not None:
            Sale.objects.filter(pk=sale.pk).update(created_at=created_at)
        return sale

    def test_today_totals_exclude_yesterday_and_before_today(self):
        start = self.local_day_start()
        self.make_sale(Decimal("999.00"), start - timedelta(minutes=1))
        self.make_sale(Decimal("100.00"), start)
        self.make_sale(Decimal("50.50"), start + timedelta(hours=1))

        data = services.get_dashboard_data()

        self.assertEqual(data["today_sales_total"], Decimal("150.50"))
        self.assertEqual(data["today_sales_count"], 2)

    def test_no_sales_today_shows_zero_not_none(self):
        start = self.local_day_start()
        self.make_sale(Decimal("40.00"), start - timedelta(days=1))

        data = services.get_dashboard_data()

        self.assertEqual(data["today_sales_total"], Decimal("0.00"))
        self.assertEqual(data["today_sales_count"], 0)

    def test_low_stock_boundary_and_active_filter(self):
        data = services.get_dashboard_data()
        low_stock = list(data["low_stock_products"])

        self.assertEqual(
            [product.pk for product in low_stock],
            [self.stock_zero.pk, self.stock_four.pk],
        )
        self.assertNotIn(self.stock_five, low_stock)
        self.assertNotIn(self.inactive, low_stock)

    def test_active_product_count_excludes_inactive_products(self):
        data = services.get_dashboard_data()

        self.assertEqual(data["active_product_count"], 4)

    def test_recent_sales_returns_five_newest_first(self):
        start = self.local_day_start()
        sales = [
            self.make_sale(
                Decimal("10.00"), start + timedelta(minutes=index)
            )
            for index in range(6)
        ]

        data = services.get_dashboard_data()
        recent = list(data["recent_sales"])

        self.assertEqual(
            [sale.pk for sale in recent],
            [sale.pk for sale in reversed(sales[1:])],
        )


class DashboardViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="dashboard-viewer", password="test-password-123"
        )
        category = Category.objects.create(name="Groceries")
        cls.low_stock = Product.objects.create(
            name="Low Stock Product",
            sku="LOW-001",
            category=category,
            barcode="",
            price=Decimal("10.00"),
            stock_quantity=4,
        )

    def test_dashboard_renders_summary_and_links(self):
        sale = Sale.objects.create(
            invoice_number="INV-TEST-00001",
            subtotal=Decimal("75.00"),
            total=Decimal("75.00"),
            created_by=self.user,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Today's sales")
        self.assertContains(response, "75.00")
        self.assertContains(response, "Low Stock Product")
        self.assertContains(
            response, reverse("products:stock", args=[self.low_stock.pk])
        )
        self.assertContains(
            response, reverse("sales:sale_detail", args=[sale.pk])
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('dashboard:home')}",
        )
