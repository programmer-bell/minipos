# AI usage log

## Step: Product management (`products` app)

- **What the AI generated:** Product list/create/edit/soft-delete views and URLs; `ProductForm`/`CategoryForm` with SKU normalization and duplicate checks; `products/services.py` with `adjust_stock()`, `create_product()`, `update_product()`, `deactivate_product()` and `create_category()`; Bootstrap templates for the list, form, delete confirmation and category form; navbar link; automated tests.
- **What to verify:** Create a product with opening stock and confirm one INITIAL `StockAdjustment` exists; duplicate SKU in a different case and a negative price both show form errors; search matches partial name/SKU; soft-deleted products disappear from the default list and reappear with "Show inactive"; editing never changes stock.
