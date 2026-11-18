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
