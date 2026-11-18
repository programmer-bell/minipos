from django.contrib import admin

from .models import Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    can_delete = False
    readonly_fields = ["product", "product_name", "sku", "unit_price", "quantity", "line_total"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ["invoice_number", "created_at", "subtotal", "discount_amount", "total"]
    search_fields = ["invoice_number"]
    inlines = [SaleItemInline]
    readonly_fields = [
        "invoice_number", "subtotal", "discount_type", "discount_value",
        "discount_amount", "total", "created_by", "created_at",
    ]

    def has_add_permission(self, request):
        return False