from django.contrib import admin

from .models import Category, Product, StockAdjustment


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "sku", "category", "price", "stock_quantity", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "sku", "barcode"]
    readonly_fields = ["stock_quantity"]  # stock changes must create history


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ["created_at", "product", "change", "stock_after", "reason", "reference"]
    list_filter = ["reason"]
    search_fields = ["product__name", "product__sku", "reference"]

    # History is append-only
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False