#!/bin/bash
set -e
echo "=== Starting TQC ==="
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
mkdir -p data
export TQC_DATA_DIR="$ROOT/data"
echo "ROOT=$ROOT  DATA=$TQC_DATA_DIR"

# Init DB + seed, then verify (all in the same process gunicorn will use)
python3 -c "
import sys, os
sys.path.insert(0, '$ROOT')
from db import init_db, get_db_path
init_db()
import sqlite3
dbp = get_db_path()
conn = sqlite3.connect(dbp)
conn.row_factory = sqlite3.Row
c = conn.execute('SELECT COUNT(*) FROM tqc__rules').fetchone()[0]
sn = conn.execute('SELECT sn,inspection_item,inspection_item_es FROM tqc__rules LIMIT 1').fetchone()
if sn:
    print(f'DB OK: {dbp}  rules={c}  sample={sn[\"sn\"]} en={sn[\"inspection_item\"][:50]} es={sn[\"inspection_item_es\"][:50]}')
else:
    print(f'DB EMPTY: {dbp}  rules={c}')
conn.close()
"
echo "--- init done ---"

exec gunicorn server:app --bind "0.0.0.0:${PORT:-8789}" --workers 1 --timeout 120 --preload
