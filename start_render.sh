#!/bin/bash
# Render start script
set -e
echo "=== Starting TQC ==="
cd "$(dirname "$0")"
mkdir -p data

echo "Init DB + seed..."
python3 -c "
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath('db.py')))
from db import init_db, get_db_path
init_db()
# Verify
import sqlite3
conn = sqlite3.connect(get_db_path())
c = conn.execute('SELECT COUNT(*) FROM tqc__rules').fetchone()[0]
print(f'DB ready: {c} rules at {get_db_path()}')
conn.close()
" || { echo "DB init failed"; exit 1; }

echo "Starting gunicorn on port ${PORT:-8789}..."
exec gunicorn server:app --bind "0.0.0.0:${PORT:-8789}" --workers 1 --timeout 120
