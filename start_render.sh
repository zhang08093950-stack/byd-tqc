#!/bin/bash
# Render start script
set -e
echo "=== Starting TQC ==="
cd "$(dirname "$0")"
mkdir -p data

echo "Starting gunicorn on port ${PORT:-8789}..."
exec gunicorn server:app --bind "0.0.0.0:${PORT:-8789}" --workers 1 --timeout 120
