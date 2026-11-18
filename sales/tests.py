from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
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


class PosViewTests(TestCase):
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
            barcode="111",
            price=Decimal("120.00"),
            stock_quantity=10,
        )
        cls.chips = Product.objects.create(
            name="Potato Chips",
            sku="SNK-001",
            category=category,
            barcode="222",
            price=Decimal("30.00"),
            stock_quantity=2,
        )
        cls.out_of_stock = Product.objects.create(
            name="Empty Shelf",
            sku="OUT-001",
            category=category,
            barcode="333",
            price=Decimal("10.00"),
            stock_quantity=0,
        )
        cls.inactive = Product.objects.create(
            name="Old Tea",
            sku="OLD-001",
            category=category,
            barcode="444",
            price=Decimal("80.00"),
            stock_quantity=5,
            is_active=False,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def set_cart(self, cart):
        session = self.client.session
        session["pos_cart"] = {
            str(product_id): quantity for product_id, quantity in cart.items()
        }
        session.save()

    def get_cart(self):
        return self.client.session.get("pos_cart", {})

    def test_pos_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("sales:pos"))

        self.assertRedirects(
            response, f"{reverse('login')}?next={reverse('sales:pos')}"
        )

    def test_navbar_links_to_pos(self):
        response = self.client.get(reverse("products:list"))

        self.assertContains(response, f'href="{reverse("sales:pos")}"')

    def test_search_matches_name_sku_and_exact_barcode(self):
        response = self.client.get(reverse("sales:pos"), {"q": "rice"})
        self.assertContains(response, "Basmati Rice")
        self.assertNotContains(response, "Potato Chips")

        response = self.client.get(reverse("sales:pos"), {"q": "SNK-001"})
        self.assertContains(response, "Potato Chips")
        self.assertNotContains(response, "Basmati Rice")

        response = self.client.get(reverse("sales:pos"), {"q": "222"})
        self.assertContains(response, "Potato Chips")

        response = self.client.get(reverse("sales:pos"), {"q": "22"})
        self.assertNotContains(response, "Potato Chips")

    def test_search_only_lists_active_products(self):
        response = self.client.get(reverse("sales:pos"), {"q": "Old Tea"})

        self.assertEqual(response.context["search_results"], [])

    def test_search_is_limited_to_ten_results(self):
        category = Category.objects.get(name="Groceries")
        for index in range(12):
            Product.objects.create(
                name=f"Search Item {index}",
                sku=f"SRCH-{index:02d}",
                category=category,
                barcode="",
                price=Decimal("1.00"),
                stock_quantity=1,
            )

        response = self.client.get(reverse("sales:pos"), {"q": "Search Item"})

        self.assertEqual(len(response.context["search_results"]), 10)

    def test_add_stores_only_product_ids_and_quantities(self):
        response = self.client.post(
            reverse("sales:pos_add", args=[self.rice.pk]), follow=True
        )

        self.assertContains(response, "Added")
        self.assertEqual(self.get_cart(), {str(self.rice.pk): 1})

    def test_add_out_of_stock_product_is_rejected(self):
        response = self.client.post(
            reverse("sales:pos_add", args=[self.out_of_stock.pk]), follow=True
        )

        self.assertContains(response, "out of stock")
        self.assertEqual(self.get_cart(), {})

    def test_add_respects_available_stock(self):
        self.set_cart({self.chips.pk: 2})

        response = self.client.post(
            reverse("sales:pos_add", args=[self.chips.pk]), follow=True
        )

        self.assertContains(response, "Only 2 unit(s)")
        self.assertEqual(self.get_cart(), {str(self.chips.pk): 2})

    def test_update_quantity_changes_cart(self):
        self.set_cart({self.rice.pk: 1})

        self.client.post(
            reverse("sales:pos_update", args=[self.rice.pk]), {"quantity": "3"}
        )

        self.assertEqual(self.get_cart(), {str(self.rice.pk): 3})

    def test_update_quantity_above_stock_is_blocked(self):
        self.set_cart({self.rice.pk: 1})

        response = self.client.post(
            reverse("sales:pos_update", args=[self.rice.pk]),
            {"quantity": "11"},
            follow=True,
        )

        self.assertContains(response, "Only 10 unit(s)")
        self.assertEqual(self.get_cart(), {str(self.rice.pk): 1})

    def test_update_quantity_below_one_is_blocked(self):
        self.set_cart({self.rice.pk: 1})

        response = self.client.post(
            reverse("sales:pos_update", args=[self.rice.pk]),
            {"quantity": "0"},
            follow=True,
        )

        self.assertContains(response, "at least 1")
        self.assertEqual(self.get_cart(), {str(self.rice.pk): 1})

    def test_remove_deletes_cart_entry(self):
        self.set_cart({self.rice.pk: 2, self.chips.pk: 1})

        response = self.client.post(
            reverse("sales:pos_remove", args=[self.rice.pk]), follow=True
        )

        self.assertContains(response, "removed from the cart")
        self.assertEqual(self.get_cart(), {str(self.chips.pk): 1})

    def test_percent_discount_preview_is_stored_and_shown(self):
        self.set_cart({self.rice.pk: 1})

        response = self.client.post(
            reverse("sales:pos_discount"),
            {"discount_type": Sale.DiscountType.PERCENT, "discount_value": "10"},
            follow=True,
        )

        self.assertContains(response, "Discount applied")
        self.assertEqual(
            self.client.session["pos_discount_type"], Sale.DiscountType.PERCENT
        )
        self.assertEqual(self.client.session["pos_discount_value"], "10.00")
        self.assertContains(response, "12.00")
        self.assertContains(response, "108.00")

    def test_flat_discount_preview_is_shown(self):
        self.set_cart({self.rice.pk: 1})

        response = self.client.post(
            reverse("sales:pos_discount"),
            {"discount_type": Sale.DiscountType.FLAT, "discount_value": "30"},
            follow=True,
        )

        self.assertContains(response, "30.00")
        self.assertContains(response, "90.00")

    def test_flat_discount_above_subtotal_is_rejected(self):
        self.set_cart({self.rice.pk: 1})

        response = self.client.post(
            reverse("sales:pos_discount"),
            {"discount_type": Sale.DiscountType.FLAT, "discount_value": "130"},
            follow=True,
        )

        self.assertContains(response, "cannot be more than the subtotal")
        self.assertNotIn("pos_discount_type", self.client.session)

    def test_percent_discount_above_100_is_rejected(self):
        self.set_cart({self.rice.pk: 1})

        response = self.client.post(
            reverse("sales:pos_discount"),
            {"discount_type": Sale.DiscountType.PERCENT, "discount_value": "101"},
            follow=True,
        )

        self.assertContains(response, "cannot be more than 100")
        self.assertNotIn("pos_discount_type", self.client.session)

    def test_checkout_completes_sale_and_clears_cart(self):
        self.set_cart({self.rice.pk: 2, self.chips.pk: 1})
        session = self.client.session
        session["pos_discount_type"] = Sale.DiscountType.PERCENT
        session["pos_discount_value"] = "10.00"
        session.save()

        response = self.client.post(
            reverse("sales:pos_checkout"),
            {"discount_type": Sale.DiscountType.PERCENT, "discount_value": "10"},
        )

        sale = Sale.objects.get()
        self.assertRedirects(response, reverse("sales:sale_detail", args=[sale.pk]))
        self.assertEqual(sale.subtotal, Decimal("270.00"))
        self.assertEqual(sale.discount_amount, Decimal("27.00"))
        self.assertEqual(sale.total, Decimal("243.00"))

        self.rice.refresh_from_db()
        self.chips.refresh_from_db()
        self.assertEqual(self.rice.stock_quantity, 8)
        self.assertEqual(self.chips.stock_quantity, 1)
        self.assertNotIn("pos_cart", self.client.session)
        self.assertNotIn("pos_discount_type", self.client.session)

        detail = self.client.get(reverse("sales:sale_detail", args=[sale.pk]))
        self.assertContains(detail, sale.invoice_number)
        self.assertContains(detail, "Basmati Rice")

    def test_checkout_after_stock_taken_elsewhere_fails_and_keeps_cart(self):
        self.set_cart({self.chips.pk: 2})
        services.checkout(
            [(self.chips.pk, 2)],
            Sale.DiscountType.NONE,
            Decimal("0"),
            self.user,
        )

        response = self.client.post(
            reverse("sales:pos_checkout"),
            {"discount_type": Sale.DiscountType.NONE, "discount_value": ""},
            follow=True,
        )

        self.assertContains(response, "has only 0 unit(s)")
        self.assertEqual(self.get_cart(), {str(self.chips.pk): 2})
        self.assertEqual(Sale.objects.count(), 1)

        self.chips.refresh_from_db()
        self.assertEqual(self.chips.stock_quantity, 0)

    def test_checkout_rejects_inactive_product_and_keeps_cart(self):
        self.set_cart({self.inactive.pk: 1})

        response = self.client.post(
            reverse("sales:pos_checkout"),
            {"discount_type": Sale.DiscountType.NONE, "discount_value": ""},
            follow=True,
        )

        self.assertContains(response, "Not available for sale")
        self.assertContains(response, "Old Tea")
        self.assertEqual(self.get_cart(), {str(self.inactive.pk): 1})
        self.assertFalse(Sale.objects.exists())

    def test_checkout_empty_cart_is_rejected(self):
        response = self.client.post(
            reverse("sales:pos_checkout"),
            {"discount_type": Sale.DiscountType.NONE, "discount_value": ""},
            follow=True,
        )

        self.assertContains(response, "The cart is empty")
        self.assertFalse(Sale.objects.exists())


class SalesViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="sales-viewer", password="test-password-123"
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
            stock_quantity=5,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def make_sale(
        self,
        items,
        discount_type=Sale.DiscountType.NONE,
        discount_value=Decimal("0"),
        created_at=None,
    ):
        sale = services.checkout(items, discount_type, discount_value, self.user)
        if created_at is not None:
            Sale.objects.filter(pk=sale.pk).update(created_at=created_at)
            sale.refresh_from_db()
        return sale

    def test_list_shows_sales_newest_first_with_item_count(self):
        first = self.make_sale([(self.rice.pk, 1)])
        second = self.make_sale([(self.chips.pk, 2)])

        response = self.client.get(reverse("sales:sale_list"))

        self.assertEqual(response.status_code, 200)
        sales = list(response.context["page_obj"].object_list)
        self.assertEqual([sale.pk for sale in sales], [second.pk, first.pk])
        self.assertEqual(sales[0].item_count, 1)
        self.assertContains(response, first.invoice_number)
        self.assertContains(response, second.invoice_number)

    def test_list_searches_by_invoice_number(self):
        first = self.make_sale([(self.rice.pk, 1)])
        second = self.make_sale([(self.chips.pk, 1)])

        response = self.client.get(
            reverse("sales:sale_list"), {"q": first.invoice_number}
        )

        self.assertContains(response, first.invoice_number)
        self.assertNotContains(response, second.invoice_number)

    def test_list_filters_by_inclusive_date_range(self):
        today = timezone.localdate()
        old_sale = self.make_sale(
            [(self.rice.pk, 1)],
            created_at=timezone.now() - timedelta(days=2),
        )
        new_sale = self.make_sale([(self.chips.pk, 1)])

        response = self.client.get(
            reverse("sales:sale_list"),
            {"date_from": today.isoformat(), "date_to": today.isoformat()},
        )
        sales = list(response.context["page_obj"].object_list)
        self.assertEqual([sale.pk for sale in sales], [new_sale.pk])

        response = self.client.get(
            reverse("sales:sale_list"),
            {
                "date_from": (today - timedelta(days=3)).isoformat(),
                "date_to": (today - timedelta(days=1)).isoformat(),
            },
        )
        sales = list(response.context["page_obj"].object_list)
        self.assertEqual([sale.pk for sale in sales], [old_sale.pk])

    def test_list_rejects_reversed_date_range(self):
        today = timezone.localdate()

        response = self.client.get(
            reverse("sales:sale_list"),
            {
                "date_from": today.isoformat(),
                "date_to": (today - timedelta(days=1)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "From date cannot be after to date")

    def test_list_paginates_at_20(self):
        for index in range(21):
            Sale.objects.create(
                invoice_number=f"INV-TEST-{index:05d}",
                subtotal=Decimal("10.00"),
                total=Decimal("10.00"),
                created_by=self.user,
            )

        response = self.client.get(reverse("sales:sale_list"))

        page_obj = response.context["page_obj"]
        self.assertEqual(len(page_obj.object_list), 20)
        self.assertEqual(page_obj.paginator.count, 21)
        self.assertEqual(page_obj.paginator.num_pages, 2)

    def test_detail_uses_snapshots_after_product_changes(self):
        sale = self.make_sale(
            [(self.rice.pk, 2)],
            Sale.DiscountType.PERCENT,
            Decimal("10"),
        )

        self.rice.name = "Renamed Rice"
        self.rice.sku = "NEW-001"
        self.rice.price = Decimal("999.00")
        self.rice.save(update_fields=["name", "sku", "price", "updated_at"])

        response = self.client.get(
            reverse("sales:sale_detail", args=[sale.pk])
        )

        self.assertContains(response, "Basmati Rice")
        self.assertNotContains(response, "Renamed Rice")
        self.assertContains(response, "GRC-001")
        self.assertNotContains(response, "NEW-001")
        self.assertContains(response, "120.00")
        self.assertContains(response, "240.00")
        self.assertContains(response, "Percentage")
        self.assertContains(response, "10.00%")
        self.assertContains(response, "24.00")
        self.assertContains(response, "216.00")
        self.assertContains(response, "sales-viewer")

    def test_detail_returns_404_for_missing_sale(self):
        response = self.client.get(
            reverse("sales:sale_detail", args=[999999])
        )

        self.assertEqual(response.status_code, 404)

    def test_detail_prefetches_items_without_n_plus_one(self):
        sale = self.make_sale([(self.rice.pk, 1), (self.chips.pk, 1)])

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                reverse("sales:sale_detail", args=[sale.pk])
            )

        self.assertEqual(response.status_code, 200)
        item_queries = [
            query["sql"]
            for query in queries.captured_queries
            if "sales_saleitem" in query["sql"].lower()
        ]
        self.assertEqual(len(item_queries), 1)

    def test_print_page_is_standalone_and_printable(self):
        sale = self.make_sale([(self.rice.pk, 2)])

        response = self.client.get(reverse("sales:sale_print", args=[sale.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, sale.invoice_number)
        self.assertContains(response, "Basmati Rice")
        self.assertContains(response, "240.00")
        self.assertContains(response, "@media print")
        self.assertContains(response, "window.print()")
        self.assertNotContains(response, "Dashboard")
        self.assertNotContains(response, "navbar")

    def test_sales_pages_require_login(self):
        sale = self.make_sale([(self.rice.pk, 1)])
        self.client.logout()

        urls = [
            reverse("sales:sale_list"),
            reverse("sales:sale_detail", args=[sale.pk]),
            reverse("sales:sale_print", args=[sale.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(
                    response, f"{reverse('login')}?next={url}"
                )
