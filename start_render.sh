#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
mkdir -p data
export TQC_DATA_DIR="$ROOT/data"
echo "ROOT=$ROOT"

# Init DB + seed
python3 -c "
import sys, os
sys.path.insert(0, '$ROOT')
from db import init_db, get_db_path, get_conn
init_db()
conn = get_conn()
c = conn.execute('SELECT COUNT(*) FROM tqc__rules').fetchone()[0]
s = conn.execute('SELECT inspection_item_es FROM tqc__rules LIMIT 1').fetchone()
conn.close()
print(f'DB OK: {get_db_path()} rules={c} es={s[0][:50] if s and s[0] else \"NONE\"}')
" || { echo "INIT FAILED"; exit 1; }

echo "Starting gunicorn..."
exec gunicorn server:app --bind "0.0.0.0:${PORT:-8789}" --workers 1 --timeout 120
