#!/bin/bash
# Render start script — init DB, import seed data, launch gunicorn

set -e

cd "$(dirname "$0")"

# Ensure data directory exists
mkdir -p data

# Initialize database tables (idempotent)
python3 -c "from db import init_db; init_db(); print('DB ready.')"

# Import seed rules with Chinese + Spanish translations
python3 seed_import.py

# Start gunicorn
exec gunicorn server:app --bind "0.0.0.0:${PORT:-8789}" --workers 2 --timeout 120
