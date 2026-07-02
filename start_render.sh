#!/bin/bash
set -e
cd "$(cd "$(dirname "$0")" && pwd)"
mkdir -p data
export TQC_DATA_DIR="$(pwd)/data"
exec gunicorn server:app --bind "0.0.0.0:${PORT:-8789}" --workers 1 --timeout 120
