from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from products.models import Category, Product, StockAdjustment
from sales import services
from sales.models import Sale, SaleItem


class CheckoutServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="cashier", password="test-password-123"
        )
        category = Category.objects.create(name="Groceries")
        cls.rice = Product.objects.create(
            name="Basmati Rice",
            sku="GRC-001",
            category=category,
            barcode="",
            price=Decimal("120.00"),
            stock_quantity=10,
        )
        cls.chips = Product.objects.create(
            name="Potato Chips",
            sku="SNK-001",
            category=category,
            barcode="",
            price=Decimal("30.00"),
            stock_quantity=2,
        )
        cls.penny = Product.objects.create(
            name="Penny Item",
            sku="STN-001",
            category=category,
            barcode="",
            price=Decimal("33.33"),
            stock_quantity=5,
        )
        cls.inactive = Product.objects.create(
            name="Old Tea",
            sku="OLD-001",
            category=category,
            barcode="",
            price=Decimal("80.00"),
            stock_quantity=5,
            is_active=False,
        )

    def test_checkout_reduces_stock_and_records_sale_history(self):
        sale = services.checkout(
            [(self.rice.pk, 2), (self.chips.pk, 1)],
            Sale.DiscountType.NONE,
            Decimal("0"),
            self.user,
        )

        self.rice.refresh_from_db()
        self.chips.refresh_from_db()
        self.assertEqual(self.rice.stock_quantity, 8)
        self.assertEqual(self.chips.stock_quantity, 1)

        self.assertEqual(sale.subtotal, Decimal("270.00"))
        self.assertEqual(sale.discount_amount, Decimal("0.00"))
        self.assertEqual(sale.total, Decimal("270.00"))
        self.assertEqual(sale.created_by, self.user)
        self.assertRegex(sale.invoice_number, r"^INV-\d{8}-\d{5}$")
        self.assertEqual(
            sale.invoice_number,
            f"INV-{timezone.localdate():%Y%m%d}-{sale.pk:05d}",
        )

        items = {item.sku: item for item in sale.items.all()}
        self.assertEqual(items["GRC-001"].product_name, "Basmati Rice")
        self.assertEqual(items["GRC-001"].unit_price, Decimal("120.00"))
        self.assertEqual(items["GRC-001"].quantity, 2)
        self.assertEqual(items["GRC-001"].line_total, Decimal("240.00"))
        self.assertEqual(items["SNK-001"].product_name, "Potato Chips")
        self.assertEqual(items["SNK-001"].unit_price, Decimal("30.00"))
        self.assertEqual(items["SNK-001"].line_total, Decimal("30.00"))

        adjustments = StockAdjustment.objects.filter(
            reason=StockAdjustment.Reason.SALE
        )
        self.assertEqual(adjustments.count(), 2)
        self.assertEqual({a.reference for a in adjustments}, {sale.invoice_number})
        self.assertEqual({a.created_by for a in adjustments}, {self.user})

        rice_adjustment = adjustments.get(product=self.rice)
        self.assertEqual(rice_adjustment.change, -2)
        self.assertEqual(rice_adjustment.stock_after, 8)

    def test_checkout_rejects_more_than_available_stock(self):
        with self.assertRaisesMessage(
            services.CheckoutError, '"Potato Chips" has only 2 unit(s)'
        ):
            services.checkout(
                [(self.chips.pk, 3)],
                Sale.DiscountType.NONE,
                Decimal("0"),
                self.user,
            )

        self.chips.refresh_from_db()
        self.assertEqual(self.chips.stock_quantity, 2)
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(SaleItem.objects.exists())
        self.assertFalse(StockAdjustment.objects.exists())

    def test_second_item_shortage_leaves_first_item_untouched(self):
        with self.assertRaises(services.CheckoutError):
            services.checkout(
                [(self.rice.pk, 3), (self.chips.pk, 5)],
                Sale.DiscountType.NONE,
                Decimal("0"),
                self.user,
            )

        self.rice.refresh_from_db()
        self.chips.refresh_from_db()
        self.assertEqual(self.rice.stock_quantity, 10)
        self.assertEqual(self.chips.stock_quantity, 2)
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(SaleItem.objects.exists())
        self.assertFalse(StockAdjustment.objects.exists())

    def test_percent_discount_is_calculated_and_rounded(self):
        sale = services.checkout(
            [(self.penny.pk, 3)],
            Sale.DiscountType.PERCENT,
            Decimal("7.5"),
            self.user,
        )

        # 33.33 * 3 = 99.99; 7.5% = 7.49925, quantized half-up to 7.50.
        self.assertEqual(sale.subtotal, Decimal("99.99"))
        self.assertEqual(sale.discount_amount, Decimal("7.50"))
        self.assertEqual(sale.total, Decimal("92.49"))

    def test_calculate_discount_handles_percent_boundaries(self):
        self.assertEqual(
            services.calculate_discount(
                Decimal("99.99"), Sale.DiscountType.PERCENT, Decimal("7.5")
            ),
            Decimal("7.50"),
        )
        self.assertEqual(
            services.calculate_discount(
                Decimal("120.00"), Sale.DiscountType.PERCENT, Decimal("100")
            ),
            Decimal("120.00"),
        )

    def test_flat_discount_is_subtracted_from_total(self):
        sale = services.checkout(
            [(self.rice.pk, 1)],
            Sale.DiscountType.FLAT,
            Decimal("50.00"),
            self.user,
        )

        self.assertEqual(sale.subtotal, Decimal("120.00"))
        self.assertEqual(sale.discount_amount, Decimal("50.00"))
        self.assertEqual(sale.total, Decimal("70.00"))

    def test_flat_discount_above_subtotal_is_rejected(self):
        with self.assertRaises(services.CheckoutError):
            services.calculate_discount(
                Decimal("120.00"), Sale.DiscountType.FLAT, Decimal("120.01")
            )
        with self.assertRaises(services.CheckoutError):
            services.checkout(
                [(self.rice.pk, 1)],
                Sale.DiscountType.FLAT,
                Decimal("120.01"),
                self.user,
            )

        self.assertFalse(Sale.objects.exists())

    def test_percent_discount_above_100_is_rejected(self):
        with self.assertRaises(services.CheckoutError):
            services.calculate_discount(
                Decimal("120.00"), Sale.DiscountType.PERCENT, Decimal("100.01")
            )

    def test_sale_item_keeps_price_snapshot_after_product_price_changes(self):
        sale = services.checkout(
            [(self.rice.pk, 1)],
            Sale.DiscountType.NONE,
            Decimal("0"),
            self.user,
        )

        self.rice.price = Decimal("999.00")
        self.rice.save(update_fields=["price", "updated_at"])

        item = sale.items.get()
        sale.refresh_from_db()
        self.assertEqual(item.unit_price, Decimal("120.00"))
        self.assertEqual(item.line_total, Decimal("120.00"))
        self.assertEqual(sale.total, Decimal("120.00"))

    def test_inactive_product_is_rejected(self):
        with self.assertRaisesMessage(services.CheckoutError, "Old Tea"):
            services.checkout(
                [(self.inactive.pk, 1)],
                Sale.DiscountType.NONE,
                Decimal("0"),
                self.user,
            )

        self.inactive.refresh_from_db()
        self.assertEqual(self.inactive.stock_quantity, 5)
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(StockAdjustment.objects.exists())

    def test_empty_cart_is_rejected(self):
        with self.assertRaisesMessage(services.CheckoutError, "cart is empty"):
            services.checkout(
                [], Sale.DiscountType.NONE, Decimal("0"), self.user
            )

        self.assertFalse(Sale.objects.exists())

    def test_quantity_below_one_is_rejected(self):
        with self.assertRaises(services.CheckoutError):
            services.checkout(
                [(self.rice.pk, 0)],
                Sale.DiscountType.NONE,
                Decimal("0"),
                self.user,
            )

        self.assertFalse(Sale.objects.exists())

    def test_duplicate_product_ids_are_merged(self):
        sale = services.checkout(
            [(self.rice.pk, 1), (self.rice.pk, 2)],
            Sale.DiscountType.NONE,
            Decimal("0"),
            self.user,
        )

        self.rice.refresh_from_db()
        self.assertEqual(self.rice.stock_quantity, 7)
        self.assertEqual(sale.items.count(), 1)
        self.assertEqual(sale.items.get().quantity, 3)
