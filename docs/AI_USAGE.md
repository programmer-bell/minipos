# AI usage log

## Step: Product management (`products` app)

- **What the AI generated:** Product list/create/edit/soft-delete views and URLs; `ProductForm`/`CategoryForm` with SKU normalization and duplicate checks; `products/services.py` with `adjust_stock()`, `create_product()`, `update_product()`, `deactivate_product()` and `create_category()`; Bootstrap templates for the list, form, delete confirmation and category form; navbar link; automated tests.
- **What to verify:** Create a product with opening stock and confirm one INITIAL `StockAdjustment` exists; duplicate SKU in a different case and a negative price both show form errors; search matches partial name/SKU; soft-deleted products disappear from the default list and reappear with "Show inactive"; editing never changes stock.

## Step: Stock adjustment and history (`products` app)

- **What the AI generated:** `adjust_stock(product_id, change, reason, user, reference, note)` with row locking and validation; refactored opening-stock creation to call it; `StockAdjustmentForm`; per-product stock adjustment page with last 10 adjustments; filterable, paginated stock history page; product list and navbar links; tests for add/remove/all-stock/error/filter/pagination cases.
- **What to verify:** Add 5 stock and confirm the stock total and history row; removing more than available shows a form error and changes nothing; removing exactly all stock is allowed; reason choices are limited to Restock and Manual correction; history filters by partial name/SKU and reason.

