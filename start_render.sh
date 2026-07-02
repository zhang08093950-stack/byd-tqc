#!/bin/bash
# Render start script

set -e
echo "=== Starting TQC ==="
cd "$(dirname "$0")"
echo "Working dir: $(pwd)"

mkdir -p data
echo "Data dir ready"

echo "Init DB..."
python3 -c "from db import init_db; init_db(); print('DB ready.')" || { echo "DB init failed"; exit 1; }

echo "Import seed..."
python3 seed_import.py || { echo "Seed import failed"; exit 1; }

echo "Starting gunicorn on port ${PORT:-8789}..."
exec gunicorn server:app --bind "0.0.0.0:${PORT:-8789}" --workers 1 --timeout 120
