from decimal import Decimal

from django import forms

from .models import Sale


class DiscountForm(forms.Form):
    """Validate POS discount fields before previewing or completing a sale."""

    discount_type = forms.ChoiceField(
        choices=Sale.DiscountType.choices,
        initial=Sale.DiscountType.NONE,
        label="Discount",
    )
    discount_value = forms.DecimalField(
        required=False,
        min_value=Decimal("0"),
        max_digits=10,
        decimal_places=2,
        label="Value",
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["discount_type"].widget.attrs.setdefault("class", "form-select")
        self.fields["discount_value"].widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("discount_type") == Sale.DiscountType.NONE:
            cleaned_data["discount_value"] = Decimal("0.00")
        elif (
            cleaned_data.get("discount_value") is None
            and not self.has_error("discount_value")
        ):
            self.add_error("discount_value", "Enter a discount value.")
        return cleaned_data


class SaleFilterForm(forms.Form):
    """Filter sales by invoice number and an inclusive local-date range."""

    q = forms.CharField(required=False, label="Invoice number")
    date_from = forms.DateField(
        required=False,
        label="From",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    date_to = forms.DateField(
        required=False,
        label="To",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")
        if date_from and date_to and date_from > date_to:
            self.add_error("date_to", "From date cannot be after to date.")
        return cleaned_data

