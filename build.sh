#!/usr/bin/env bash
set -o errexit

# Render adds uv automatically because uv.lock is in the repo root.
uv sync --frozen --no-dev

uv run python manage.py collectstatic --noinput
uv run python manage.py migrate --noinput
uv run python manage.py seed