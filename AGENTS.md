# MiniPOS: project rules

Retail POS for a technical assessment (Django web developer intern). Reliability, clear structure and explainable code matter more than extra features.

## Stack
- Python 3.14 managed by uv (never use pip or system Python). Django 6, Django templates, Bootstrap 5 via CDN, no JS framework.
- PostgreSQL on Neon via DATABASE_URL (dj-database-url). Secrets come from .env, never hard-coded.
- Run everything through `uv run`. Add dependencies with `uv add`, and ask me before adding any.

## Layout
- `config/` settings and root urls. Apps: `products`, `sales`, `dashboard`. Templates live in the top-level `templates/` folder, extending `templates/base.html`.
- Login is required by default (LoginRequiredMiddleware). Only mark a view `@login_not_required` if it must be public.

## Rules (do not break)
- Money is always `Decimal`, never float. Quantize to 2 places with ROUND_HALF_UP.
- Business logic lives in `services.py` inside each app. Views stay thin: parse input, call a service, render or redirect.
- `Product.stock_quantity` changes ONLY through `products.services.adjust_stock()`, which writes a `StockAdjustment` row in the same transaction. Never edit stock anywhere else.
- Checkout is one `transaction.atomic()` block. Lock product rows with `select_for_update()` in order of id. Use prices from the database, never from the client or session.
- `SaleItem` stores snapshots (name, sku, unit_price). Never recompute old invoices from the live product.
- Products are soft-deleted (`is_active=False`). Never hard-delete products. All state-changing actions use POST with CSRF.
- Do not change existing models or migrations without asking me first.
- Server-side validation on every form. Show errors in the template.
- Keep code simple and readable. No clever abstractions, no unused code. Add a short docstring to every service function explaining the business rule.

## Workflow
- Work on one step per prompt. When finished, run `uv run python manage.py check` and `uv run python manage.py test`.
- End each step with a summary of 10 lines or fewer: files changed and the key design decision.
- Append one entry per step to `docs/AI_USAGE.md` (create it if missing): step name, what the AI generated, what I need to verify.