# MiniPOS Retail Billing System

## Project overview

MiniPOS is a small, server-rendered point-of-sale application built for the MiniPOS Retail technical assessment. It supports product and inventory management, checkout with discounts, sales history, printable invoices, and a daily dashboard.

- **Repository:** https://github.com/programmer-bell/minipos
- **Live application:** `<LIVE_APPLICATION_URL>`

## Features

- Create, edit, search, and deactivate products; manage categories and product barcodes.
- Search products by name or SKU in product management. POS search accepts name, SKU, or an exact barcode match.
- Build a cart, change quantities, remove items, preview flat or percentage discounts, and complete checkout.
- Validate stock before checkout and record stock changes and their history.
- Browse completed sales by invoice number and inclusive date range; open sale details and print invoices.
- Dashboard for today's sales and transaction count, active product count, products with stock below five, and the five most recent sales.
- Login-protected application views, server-side form validation, and automated tests.

## Tech stack

- Python 3.14, managed with [uv](https://docs.astral.sh/uv/)
- Django 6.1
- PostgreSQL (including Neon deployments), `psycopg`, and `dj-database-url`
- Django templates and Bootstrap 5 via CDN; no frontend framework
- WhiteNoise for static files and Gunicorn for serving the deployed application

## Local setup

Install `uv`, make sure a PostgreSQL database is available, then run:

```bash
git clone https://github.com/programmer-bell/minipos.git
cd minipos
uv sync
cp .env.example .env
```

Edit `.env` with a valid `SECRET_KEY`, a reachable PostgreSQL `DATABASE_URL`, and your preferred demo credentials (see [Environment variables](#environment-variables)). Then initialize the database, add the sample data, and start Django:

```bash
uv run python manage.py migrate
uv run python manage.py seed
uv run python manage.py runserver
```

Open http://127.0.0.1:8000/ and sign in with the demo credentials configured before running the seed command. The seed command creates sample categories and products and creates a superuser only if that username does not already exist. It does not create sample sales.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Required Django signing key. Use a unique, securely generated value outside local development. |
| `DEBUG` | Enables Django debug mode only when set to `True`; defaults to `False`. |
| `DATABASE_URL` | PostgreSQL connection URL, for example `postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require`. |
| `ALLOWED_HOSTS` | Optional comma-separated hostnames. |
| `CSRF_TRUSTED_ORIGINS` | Optional comma-separated origins including scheme, such as `https://example.onrender.com`. |
| `RENDER_EXTERNAL_HOSTNAME` | Optional Render hostname; settings add it to allowed hosts and add its HTTPS origin for CSRF. |
| `DEMO_USERNAME` | Username created by `seed` if it does not already exist. The command defaults to `demo`. |
| `DEMO_PASSWORD` | Password for the newly created seeded user. The command defaults to `demo12345`. |

Set `DEMO_USERNAME` and `DEMO_PASSWORD` explicitly before seeding, and replace the example values in `.env.example`. The seed command does not change the password of an existing user.

## Running tests

```bash
uv run python manage.py test
```

The test database is managed by Django. A PostgreSQL configuration is recommended to exercise the same database behavior as deployment.

## Demo credentials

- **Username:** `<DEMO_USERNAME>`
- **Password:** `<DEMO_PASSWORD>`

These are placeholders, not published credentials. Set both variables in `.env` before running `uv run python manage.py seed`. If those variables are omitted, the seed command uses its code defaults (`demo` / `demo12345`); do not use those defaults for a public deployment.

## Database design summary

The application tables are:

| Table | Purpose |
| --- | --- |
| `products_category` | Named product categories. |
| `products_product` | Product identity, category, barcode, current price, stock, and active state. |
| `products_stockadjustment` | Signed stock changes, resulting stock, reason, optional invoice reference/note, user, and timestamp. |
| `sales_sale` | Invoice number, totals, discount details, creator, and timestamp. |
| `sales_saleitem` | Products and quantities sold, line totals, and invoice-time product details. |

Django's built-in authentication and session tables are also used. Schema changes are tracked in Django migrations, including the initial products and sales migrations.

`SaleItem` stores the product name, SKU, and unit price as snapshots. This keeps old invoices accurate if a product is renamed, its SKU changes, or its price changes later. Its product relation is also protected from hard deletion.

Products are deactivated with `is_active=False` rather than deleted. This preserves references from sales and stock history; it also means a deactivated product's SKU remains reserved. Stock changes go through `products.services.adjust_stock()`, which updates the product and writes a `StockAdjustment` in one transaction.

Database-level constraints back up important rules: category names and SKUs are unique, nonblank barcodes are unique, product prices cannot be negative, stock uses a positive-integer field, stock adjustments cannot have a zero change, sale discounts cannot exceed the subtotal, sale totals cannot be negative, and sale-item quantities must be positive. A product can appear only once per sale. Related product/category records use protected foreign keys where preserving history matters.

## Technical decisions

- Checkout runs in one database transaction. It locks product rows in ascending ID order, takes prices from the database, checks active state and available stock, then writes the sale, snapshot items, and stock adjustments. A failure rolls the checkout back.
- Monetary values use `Decimal` fields and two-decimal `ROUND_HALF_UP` rounding; client/session cart data contains product IDs and quantities, not authoritative prices.
- Business operations live in app-level `services.py` files; views handle request input, call services, then render or redirect.
- Django templates keep the UI server-rendered and straightforward to maintain for the assessment.
- `Asia/Kolkata` is the configured application timezone; the dashboard's “today” totals use that local date boundary.
- `uv.lock` pins the dependency resolution. The Render build script syncs dependencies, collects static files, applies migrations, and runs the seed command.

## AI tools used

GitHub Copilot was used as an AI coding assistant during development. Assistance covered product and stock management, checkout and sales workflows, dashboard behavior, tests, and deployment configuration. The project keeps a more detailed task-by-task record in [`docs/AI_USAGE.md`](docs/AI_USAGE.md). The submitted code should still be reviewed and understood by the developer.

## Known limitations

- A soft-deleted product's SKU stays reserved because the product row remains and SKU uniqueness applies to all products.
- No refunds, returns, voids, or post-checkout sale editing are implemented.
- There are no multi-user roles or granular permissions; the app requires login but does not distinguish cashier and administrator capabilities.
- The seed command creates a demo superuser, not a limited cashier account, and does not create demo sales.
- There is no payment gateway, receipt email, or data export workflow.
- Barcode matching is exact text search; dedicated scanner integration is not implemented.
- Neon availability and response time depend on the selected Neon plan and its compute lifecycle; a sleeping database may add cold-start latency.
- `products.services.adjust_stock()` uses database row locking for concurrent stock changes. Use PostgreSQL for deployment; SQLite does not provide equivalent row-locking behavior.
