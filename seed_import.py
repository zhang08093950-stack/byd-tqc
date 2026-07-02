"""Import seed rules from seed_rules.json into the database."""
import json
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from db import get_conn

def import_seed():
    seed_path = os.path.join(BASE_DIR, 'seed_rules.json')
    print(f"[seed] Looking for {seed_path}", file=sys.stderr)
    if not os.path.exists(seed_path):
        print(f"[seed] ERROR: seed_rules.json not found at {seed_path}", file=sys.stderr)
        sys.exit(1)

    with open(seed_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    conn = get_conn()
    cols = data['columns']
    placeholders = ','.join(['?'] * len(cols))
    col_names = ','.join(cols)

    conn.execute("DELETE FROM tqc__rules")
    for row in data['rows']:
        vals = [row[c] for c in cols]
        conn.execute(
            f"INSERT INTO tqc__rules ({col_names}) VALUES ({placeholders})",
            vals
        )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM tqc__rules").fetchone()[0]
    conn.close()
    print(f"[seed] Imported: {count} rules", file=sys.stderr)

if __name__ == '__main__':
    import_seed()
