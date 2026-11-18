# AI usage log

## Step: Product management (`products` app)

- **What the AI generated:** Product list/create/edit/soft-delete views and URLs; `ProductForm`/`CategoryForm` with SKU normalization and duplicate checks; `products/services.py` with `adjust_stock()`, `create_product()`, `update_product()`, `deactivate_product()` and `create_category()`; Bootstrap templates for the list, form, delete confirmation and category form; navbar link; automated tests.
- **What to verify:** Create a product with opening stock and confirm one INITIAL `StockAdjustment` exists; duplicate SKU in a different case and a negative price both show form errors; search matches partial name/SKU; soft-deleted products disappear from the default list and reappear with "Show inactive"; editing never changes stock.

## Step: Stock adjustment and history (`products` app)

- **What the AI generated:** `adjust_stock(product_id, change, reason, user, reference, note)` with row locking and validation; refactored opening-stock creation to call it; `StockAdjustmentForm`; per-product stock adjustment page with last 10 adjustments; filterable, paginated stock history page; product list and navbar links; tests for add/remove/all-stock/error/filter/pagination cases.
- **What to verify:** Add 5 stock and confirm the stock total and history row; removing more than available shows a form error and changes nothing; removing exactly all stock is allowed; reason choices are limited to Restock and Manual correction; history filters by partial name/SKU and reason.

## Step: Checkout business logic (`sales` app)

- **What the AI generated:** `sales/services.py` with `CheckoutError`, `calculate_discount()` (flat/percent validation, ROUND_HALF_UP, capped at subtotal) and an atomic `checkout()` that merges duplicate items, locks products in id order, validates active state and stock, uses database prices, writes invoice `INV-YYYYMMDD-<pk>`, creates snapshot `SaleItem` rows and reduces stock through `products.services.adjust_stock()`; tests for successful sales, insufficient stock and rollback, discounts, price snapshots and inactive products.
- **What to verify:** Complete a sale and confirm stock, invoice number, totals and SALE history rows; try an oversold two-item cart and confirm nothing changed; check 7.5% of 99.99 gives 7.50; change a product price after a sale and confirm the old invoice is unchanged; inactive products are rejected.

## Step: POS screen (`sales` app)

- **What the AI generated:** `/pos/` with session cart (`{product_id: quantity}` only), active-product search by name/SKU/exact barcode limited to 10 results, add/update/remove cart actions, server-rendered discount preview, `DiscountForm`, checkout through `sales.services.checkout()`, a minimal sale detail page, POS navbar link, Bootstrap error alert styling, and view tests.
- **What to verify:** Add products and update quantities; try a quantity above stock and confirm it is blocked with a message; apply 10% and a flat discount and check the totals; complete a sale and confirm the cart clears, the invoice page opens, and stock drops; open POS in two tabs, sell the last unit in one, and confirm the other fails with a clear message instead of overselling.

## Step: Sales history and printable invoices (`sales` app)

- **What the AI generated:** `/sales/` with paginated newest-first sales, invoice search, inclusive date-range filter and item counts; upgraded `/sales/<id>/` using `SaleItem` snapshots with the full discount breakdown; `/sales/<id>/print/` standalone print template with `@media print` and `window.print()`; Sales navbar link; `SaleFilterForm`; query optimization with `select_related`/`prefetch_related`; tests for ordering, filters, snapshots, print output and login protection.
- **What to verify:** Totals on the list/detail/print pages match the POS receipt; change a product's name, SKU or price after a sale and confirm the old invoice is unchanged; search by invoice and filter by a date range; print preview has no navbar and hides the Print button.

## Step: Real dashboard (`dashboard` app)

- **What the AI generated:** `dashboard/services.py` with database-aggregated today's sales (local `Asia/Kolkata` day boundary), active product count, low-stock query (`active`, stock < 5, ascending) and five most recent sales; a thin dashboard view; Bootstrap cards plus low-stock and recent-sales tables with links; service and view tests.
- **What to verify:** Today's total and transaction count ignore yesterday's sales and show `0.00` when there are none; a product with stock exactly 5 is not listed as low stock while stock 4 and 0 are; inactive products are excluded; low-stock and invoice links open the right pages.

## Step: Assessment checklist test review

- **What the AI generated:** Reviewed the existing suite against the assessment checklist and added only the missing tests: the PostgreSQL negative-stock constraint, anonymous dashboard access redirecting to login, and soft-deleted products being rejected by the POS add endpoint.
- **What to verify:** Run the full suite and confirm the three new tests pass without changing any existing test; confirm the earlier tests already cover duplicate-SKU case handling, service-level negative stock, checkout rollback consistency, product search, and the other login checks.

## Step 13: Prepare for production deployment on Render with Neon PostgreSQL

- **What the AI generated:** Added `gunicorn` and `whitenoise` dependencies; updated `config/settings.py` with WhiteNoise middleware, `STATIC_ROOT`, Django 6 `STORAGES` (default FileSystemStorage and staticfiles CompressedManifestStaticFilesStorage), `RENDER_EXTERNAL_HOSTNAME` handling for `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`, and production-only security settings when `DEBUG` is False; expanded `.env.example` with deployment/demo variables; added executable `build.sh` (`uv sync --frozen --no-dev`, `collectstatic`, `migrate`, `seed`) with a marked TODO for uv installation.
- **What to verify:** With `DEBUG=True`, local HTTP still works; with `DEBUG=False` and required env vars, `manage.py check --deploy` reflects only intentional remaining warnings; `collectstatic --noinput --dry-run` succeeds; confirm Render env vars/hostname and review the `build.sh` uv-install TODO before deployment.
