import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from products.models import Category, Product, StockAdjustment

# (name, sku, category, barcode, price, stock)
PRODUCTS = [
    ("Basmati Rice 1kg", "GRC-001", "Groceries", "8901000000011", "120.00", 50),
    ("Toor Dal 1kg", "GRC-002", "Groceries", "8901000000028", "140.00", 40),
    ("Sunflower Oil 1L", "GRC-003", "Groceries", "8901000000035", "165.00", 25),
    ("Sugar 1kg", "GRC-004", "Groceries", "8901000000042", "48.00", 3),
    ("Orange Juice 1L", "BEV-001", "Beverages", "8901000000059", "95.00", 30),
    ("Cola 750ml", "BEV-002", "Beverages", "8901000000066", "40.00", 60),
    ("Green Tea 25 bags", "BEV-003", "Beverages", "8901000000073", "180.00", 4),
    ("Potato Chips 100g", "SNK-001", "Snacks", "8901000000080", "30.00", 80),
    ("Chocolate Bar 50g", "SNK-002", "Snacks", "8901000000097", "50.00", 70),
    ("Salted Peanuts 200g", "SNK-003", "Snacks", "", "60.00", 2),
    ("Bath Soap 100g", "PCR-001", "Personal Care", "8901000000103", "38.00", 45),
    ("Shampoo 340ml", "PCR-002", "Personal Care", "8901000000110", "250.00", 15),
    ("Notebook A5", "STN-001", "Stationery", "8901000000127", "55.00", 35),
    ("Ball Pen (Blue)", "STN-002", "Stationery", "8901000000134", "10.00", 0),
]


class Command(BaseCommand):
    help = "Seed demo categories, products and a demo user. Safe to run repeatedly."

    @transaction.atomic
    def handle(self, *args, **options):
        created_products = 0

        for name, sku, category_name, barcode, price, stock in PRODUCTS:
            category, _ = Category.objects.get_or_create(name=category_name)
            product, created = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "category": category,
                    "barcode": barcode,
                    "price": price,
                    "stock_quantity": stock,
                },
            )
            if created:
                created_products += 1
                if stock > 0:  # change=0 would violate our check constraint
                    StockAdjustment.objects.create(
                        product=product,
                        change=stock,
                        stock_after=stock,
                        reason=StockAdjustment.Reason.INITIAL,
                        note="Seeded demo data",
                    )

        User = get_user_model()
        username = os.environ.get("DEMO_USERNAME", "demo")
        password = os.environ.get("DEMO_PASSWORD", "demo12345")
        user_created = False
        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username=username, password=password)
            user_created = True

        self.stdout.write(self.style.SUCCESS(
            f"Seed complete: {created_products} new products, "
            f"demo user {'created' if user_created else 'already existed'}."
        ))