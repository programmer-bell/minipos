from django import forms

from .models import Category, Product


def _style_fields(fields):
    for field in fields.values():
        if isinstance(field.widget, forms.Select):
            field.widget.attrs.setdefault("class", "form-select")
        else:
            field.widget.attrs.setdefault("class", "form-control")


class ProductForm(forms.ModelForm):
    """Validate product details; opening stock is only accepted when creating."""

    class Meta:
        model = Product
        fields = ["name", "sku", "category", "barcode", "price", "stock_quantity"]
        widgets = {
            "price": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields.pop("stock_quantity")
        else:
            self.fields["stock_quantity"] = forms.IntegerField(
                min_value=0,
                initial=0,
                label="Initial stock",
                help_text="Opening stock is recorded as an initial stock adjustment.",
            )
        _style_fields(self.fields)

    def clean_sku(self):
        sku = self.cleaned_data["sku"].strip().upper()
        if not sku:
            raise forms.ValidationError("SKU is required.")

        duplicates = Product.objects.filter(sku=sku)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError(f'A product with SKU "{sku}" already exists.')
        return sku

    def clean_barcode(self):
        barcode = self.cleaned_data["barcode"].strip()
        if barcode:
            duplicates = Product.objects.filter(barcode=barcode)
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise forms.ValidationError(
                    "A product with this barcode already exists."
                )
        return barcode


class CategoryForm(forms.ModelForm):
    """Validate a category name, including the unique-name rule."""

    class Meta:
        model = Category
        fields = ["name"]
        error_messages = {
            "name": {"unique": "A category with this name already exists."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self.fields)
