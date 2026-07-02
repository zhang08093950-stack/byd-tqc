#!/bin/bash
# Render start script — init DB and launch gunicorn

set -e

cd "$(dirname "$0")"

# Ensure data directory exists
mkdir -p data

# Initialize database tables (idempotent)
python3 -c "from db import init_db, get_db_path; init_db(); print('DB ready.')"

# Import seed rules (Chinese + Spanish translations) if DB is empty
DB_PATH=$(python3 -c "from db import get_db_path; print(get_db_path())")
if [ -f seed_rules.sql ]; then
    RULE_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM tqc__rules;" 2>/dev/null || echo 0)
    if [ "$RULE_COUNT" -eq 0 ]; then
        echo "Importing seed rules with translations..."
        sqlite3 "$DB_PATH" < seed_rules.sql
        echo "Seed rules imported."
    fi
fi

# Start gunicorn
exec gunicorn server:app --bind "0.0.0.0:${PORT:-8789}" --workers 2 --timeout 120
