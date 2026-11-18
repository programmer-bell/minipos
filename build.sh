#!/usr/bin/env bash
set -o errexit

# TODO(Render): install uv here if Render does not provide it — command to be confirmed

# Sync dependencies from uv.lock without dev packages.
uv sync --frozen --no-dev

# Collect static files, apply migrations, and seed demo data.
uv run python manage.py collectstatic --noinput
uv run python manage.py migrate --noinput
uv run python manage.py seed
