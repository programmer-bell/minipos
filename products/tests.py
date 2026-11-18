from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from products import services
from products.models import Category, Product, StockAdjustment


class ProductViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="tester", password="test-password-123"
        )
        cls.category = Category.objects.create(name="Groceries")
        cls.rice = Product.objects.create(
            name="Basmati Rice",
            sku="GRC-001",
            category=cls.category,
            barcode="111",
            price=Decimal("120.00"),
            stock_quantity=10,
        )
        cls.chips = Product.objects.create(
            name="Potato Chips",
            sku="SNK-001",
            category=cls.category,
            barcode="",
            price=Decimal("30.00"),
            stock_quantity=2,
        )
        cls.inactive = Product.objects.create(
            name="Old Tea",
            sku="OLD-001",
            category=cls.category,
            barcode="",
            price=Decimal("80.00"),
            stock_quantity=0,
            is_active=False,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def product_data(self, **overrides):
        data = {
            "name": "Orange Juice",
            "sku": "bev-001",
            "category": self.category.pk,
            "barcode": "222",
            "price": "95.00",
            "stock_quantity": "5",
        }
        data.update(overrides)
        return data

    def test_login_is_required(self):
        self.client.logout()
        response = self.client.get(reverse("products:list"))
        self.assertRedirects(
            response, f"{reverse('login')}?next={reverse('products:list')}"
        )

    def test_create_product_records_initial_stock_adjustment(self):
        response = self.client.post(reverse("products:create"), self.product_data())

        self.assertRedirects(response, reverse("products:list"))
        product = Product.objects.get(sku="BEV-001")
        self.assertEqual(product.stock_quantity, 5)
        self.assertEqual(product.price, Decimal("95.00"))

        adjustment = product.adjustments.get()
        self.assertEqual(adjustment.change, 5)
        self.assertEqual(adjustment.stock_after, 5)
        self.assertEqual(adjustment.reason, StockAdjustment.Reason.INITIAL)
        self.assertEqual(adjustment.created_by, self.user)

    def test_create_with_zero_stock_writes_no_adjustment(self):
        response = self.client.post(
            reverse("products:create"), self.product_data(stock_quantity="0")
        )

        self.assertRedirects(response, reverse("products:list"))
        product = Product.objects.get(sku="BEV-001")
        self.assertEqual(product.stock_quantity, 0)
        self.assertFalse(product.adjustments.exists())

    def test_duplicate_sku_in_different_case_shows_form_error(self):
        response = self.client.post(
            reverse("products:create"),
            self.product_data(sku="grc-001", barcode="333"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("sku", response.context["form"].errors)
        self.assertContains(response, "already exists")
        self.assertFalse(Product.objects.filter(name="Orange Juice").exists())

    def test_negative_price_shows_form_error(self):
        response = self.client.post(
            reverse("products:create"), self.product_data(price="-1.00")
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("price", response.context["form"].errors)
        self.assertFalse(Product.objects.filter(sku="BEV-001").exists())

    def test_duplicate_barcode_shows_form_error(self):
        response = self.client.post(
            reverse("products:create"), self.product_data(barcode="111")
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("barcode", response.context["form"].errors)
        self.assertFalse(Product.objects.filter(sku="BEV-001").exists())

    def test_blank_barcode_can_be_reused(self):
        response = self.client.post(
            reverse("products:create"), self.product_data(barcode="")
        )

        self.assertRedirects(response, reverse("products:list"))
        self.assertTrue(Product.objects.filter(sku="BEV-001").exists())

    def test_edit_hides_stock_field_and_keeps_stock(self):
        response = self.client.get(reverse("products:edit", args=[self.rice.pk]))
        self.assertNotContains(response, 'name="stock_quantity"')

        response = self.client.post(
            reverse("products:edit", args=[self.rice.pk]),
            {
                "name": "Basmati Rice Premium",
                "sku": "grc-001",
                "category": self.category.pk,
                "barcode": "111",
                "price": "130.00",
            },
        )

        self.assertRedirects(response, reverse("products:list"))
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.name, "Basmati Rice Premium")
        self.assertEqual(self.rice.sku, "GRC-001")
        self.assertEqual(self.rice.price, Decimal("130.00"))
        self.assertEqual(self.rice.stock_quantity, 10)
        self.assertFalse(self.rice.adjustments.exists())

    def test_search_by_partial_name_and_sku(self):
        response = self.client.get(reverse("products:list"), {"q": "rice"})
        self.assertContains(response, "Basmati Rice")
        self.assertNotContains(response, "Potato Chips")

        response = self.client.get(reverse("products:list"), {"q": "snk-0"})
        self.assertContains(response, "Potato Chips")
        self.assertNotContains(response, "Basmati Rice")

    def test_inactive_products_are_hidden_by_default(self):
        response = self.client.get(reverse("products:list"))
        self.assertNotContains(response, "Old Tea")

        response = self.client.get(
            reverse("products:list"), {"show_inactive": "1"}
        )
        self.assertContains(response, "Old Tea")

    def test_delete_get_shows_confirmation_without_deactivating(self):
        response = self.client.get(reverse("products:delete", args=[self.rice.pk]))

        self.assertEqual(response.status_code, 200)
        self.rice.refresh_from_db()
        self.assertTrue(self.rice.is_active)

    def test_delete_post_soft_deletes_product(self):
        response = self.client.post(
            reverse("products:delete", args=[self.rice.pk]), follow=True
        )

        self.assertContains(response, "was deactivated")
        self.rice.refresh_from_db()
        self.assertFalse(self.rice.is_active)
        self.assertTrue(Product.objects.filter(pk=self.rice.pk).exists())

    def test_product_list_paginates_at_20(self):
        for index in range(25):
            Product.objects.create(
                name=f"Paged Product {index}",
                sku=f"PAGE-{index:03d}",
                category=self.category,
                barcode="",
                price=Decimal("1.00"),
                stock_quantity=1,
            )

        response = self.client.get(reverse("products:list"))

        page_obj = response.context["page_obj"]
        self.assertEqual(len(page_obj.object_list), 20)
        self.assertEqual(page_obj.paginator.num_pages, 2)

    def test_category_can_be_created(self):
        response = self.client.post(
            reverse("products:category_create"), {"name": "Beverages"}
        )

        self.assertRedirects(response, reverse("products:create"))
        self.assertTrue(Category.objects.filter(name="Beverages").exists())


class StockServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Groceries")
        cls.product = Product.objects.create(
            name="Rice",
            sku="GRC-100",
            category=category,
            barcode="",
            price=Decimal("10.00"),
            stock_quantity=10,
        )

    def test_adjust_stock_updates_quantity_and_writes_adjustment(self):
        adjustment = services.adjust_stock(
            self.product, -3, StockAdjustment.Reason.CORRECTION
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 7)
        self.assertEqual(adjustment.stock_after, 7)
        self.assertEqual(adjustment.change, -3)

    def test_adjust_stock_rejects_zero_change(self):
        with self.assertRaises(ValidationError):
            services.adjust_stock(
                self.product, 0, StockAdjustment.Reason.CORRECTION
            )

    def test_adjust_stock_rejects_negative_result(self):
        with self.assertRaises(ValidationError):
            services.adjust_stock(
                self.product, -11, StockAdjustment.Reason.CORRECTION
            )

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        self.assertFalse(self.product.adjustments.exists())
