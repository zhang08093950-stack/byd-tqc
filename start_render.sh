#!/bin/bash
# Render start script
set -e
echo "=== Starting TQC ==="
cd "$(dirname "$0")"
mkdir -p data

ROOT=$(pwd)
export TQC_DATA_DIR="$ROOT/data"
echo "TQC_DATA_DIR=$TQC_DATA_DIR"
echo "Files: $(ls seed_rules.json data/ 2>&1)"

echo "Starting gunicorn on port ${PORT:-8789}..."
exec gunicorn server:app --bind "0.0.0.0:${PORT:-8789}" --workers 1 --timeout 120
