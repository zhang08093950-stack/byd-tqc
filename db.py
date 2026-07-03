"""
tqc/db — SQLite database layer for TQC (Total Quality Control) scoring.

Plain functions, no ORM, sqlite3 directly.  Follows the same patterns as
the scripts/ modules (nps_db, etc.).
"""

import os
import sqlite3
from flask import g

# On Render: /opt/render/project/src/data/
# Locally: project/data/
_BASE = "/opt/render/project/src" if os.path.exists("/opt/render/project/src") else os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_BASE, "data")
DEFAULT_DB = os.path.join(DATA_DIR, "uruguay.db")
COUNTRY_DB = {
    "Uruguay":  os.path.join(DATA_DIR, "uruguay.db"),
    "Paraguay": os.path.join(DATA_DIR, "Paraguay.db"),
    "Bolivia":  os.path.join(DATA_DIR, "Bolivia.db"),
}


def get_db_path():
    """Return the current database path based on the active country."""
    import sys
    try:
        path = g.get("db_path", DEFAULT_DB)
    except RuntimeError:
        path = DEFAULT_DB
    # DEBUG
    print(f"[get_db_path] g.db_path={path}  DEFAULT_DB={DEFAULT_DB}", file=sys.stderr, flush=True)
    return path


def get_conn():
    """Return a sqlite3 connection with row_factory=Row and FK on."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create the 4 TQC tables if they don't already exist. Set WAL mode."""
    conn = get_conn()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS tqc__rules (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            sn            TEXT NOT NULL,
            category      TEXT,
            category_zh   TEXT,
            category_es   TEXT,
            inspection_item  TEXT NOT NULL,
            inspection_item_zh TEXT,
            inspection_item_es TEXT,
            inspection_way   TEXT NOT NULL,
            inspection_way_zh TEXT,
            inspection_standard TEXT,
            inspection_standard_zh TEXT,
            inspection_standard_es TEXT,
            rating_explanation TEXT,
            rating_explanation_zh TEXT,
            rating_explanation_es TEXT,
            max_score     INTEGER DEFAULT 100,
            sort_order    INTEGER DEFAULT 0,
            sheet_name    TEXT NOT NULL,
            created_at    TEXT DEFAULT (datetime('now')),
            updated_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(sn, sheet_name)
        );

        CREATE TABLE IF NOT EXISTS tqc__scores (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_sn       TEXT NOT NULL,
            workshop      TEXT NOT NULL,
            score         INTEGER,
            max_score     INTEGER DEFAULT 100,
            auto_score    INTEGER,
            auto_reason   TEXT,
            confirmed     INTEGER DEFAULT 0,
            remarks       TEXT,
            evidence_ids  TEXT DEFAULT '[]',
            created_at    TEXT DEFAULT (datetime('now')),
            updated_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(rule_sn, workshop)
        );

        CREATE TABLE IF NOT EXISTS tqc__evidence (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_sn       TEXT NOT NULL,
            workshop      TEXT NOT NULL,
            filename      TEXT,
            mime_type     TEXT,
            data          BLOB,
            thumbnail     BLOB,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tqc__monthly (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            month           TEXT NOT NULL,
            workshop        TEXT NOT NULL,
            total_score     INTEGER,
            total_max_score INTEGER,
            score_pct       REAL,
            rank            INTEGER,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now')),
            UNIQUE(month, workshop)
        );
    """)
        # Migrate: add columns that may be missing from older schema
        for col in [
            "category_zh TEXT", "category_es TEXT",
            "inspection_item_zh TEXT", "inspection_item_es TEXT",
            "inspection_way_zh TEXT",
            "inspection_standard_zh TEXT", "inspection_standard_es TEXT",
            "rating_explanation TEXT", "rating_explanation_zh TEXT", "rating_explanation_es TEXT",
        ]:
            try:
                conn.execute(f"ALTER TABLE tqc__rules ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass  # column already exists

        # Import seed data if rules table is empty
        count = conn.execute("SELECT COUNT(*) FROM tqc__rules").fetchone()[0]
        if count == 0:
            _import_seed(conn)

        conn.commit()
    finally:
        conn.close()


def _import_seed(conn):
    """Import seed rules from seed_rules.json if available."""
    import json, os, sys
    seed_path = os.path.join(_BASE, 'seed_rules.json')
    if not os.path.exists(seed_path):
        print(f"[seed] No seed file at {seed_path}", file=sys.stderr)
        return
    with open(seed_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    cols = data['columns']
    placeholders = ','.join(['?'] * len(cols))
    col_names = ','.join(cols)
    for row in data['rows']:
        vals = [row[c] for c in cols]
        conn.execute(
            f"INSERT OR IGNORE INTO tqc__rules ({col_names}) VALUES ({placeholders})",
            vals
        )
    print(f"[seed] Imported {len(data['rows'])} rules", file=sys.stderr)


def _quarter_sheet(quarter):
    """Map quarter string like '2026 Q2' to sheet name like '2026 Q2 Quarterly TQC'."""
    return f"{quarter} Quarterly TQC"


def all_rules(quarter=None):
    """Return all rules ordered by sort_order, optionally filtered by quarter."""
    conn = get_conn()
    try:
        if quarter:
            sheet = _quarter_sheet(quarter)
            rows = conn.execute(
                "SELECT * FROM tqc__rules WHERE sheet_name = ? ORDER BY sort_order",
                (sheet,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tqc__rules ORDER BY sort_order"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def rules_by_way(way, quarter=None):
    """Return rules filtered by inspection_way, optionally by quarter."""
    conn = get_conn()
    try:
        if quarter:
            sheet = _quarter_sheet(quarter)
            rows = conn.execute(
                "SELECT * FROM tqc__rules WHERE inspection_way = ? AND sheet_name = ? ORDER BY sort_order",
                (way, sheet)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tqc__rules WHERE inspection_way = ? ORDER BY sort_order",
                (way,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def scores_for_workshop(workshop):
    """Return all scores for a workshop as a dict keyed by rule_sn."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tqc__scores WHERE workshop = ?",
            (workshop,)
        ).fetchall()
        return {r["rule_sn"]: dict(r) for r in rows}
    finally:
        conn.close()


def upsert_score(rule_sn, workshop, score, max_score, auto_score,
                 auto_reason, confirmed, remarks):
    """Insert a score row or update it on (rule_sn, workshop) conflict."""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO tqc__scores
                (rule_sn, workshop, score, max_score, auto_score,
                 auto_reason, confirmed, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_sn, workshop) DO UPDATE SET
                score       = excluded.score,
                max_score   = excluded.max_score,
                auto_score  = excluded.auto_score,
                auto_reason = excluded.auto_reason,
                confirmed   = excluded.confirmed,
                remarks     = excluded.remarks,
                updated_at  = datetime('now')
        """, (rule_sn, workshop, score, max_score, auto_score,
              auto_reason, confirmed, remarks))
        conn.commit()
    finally:
        conn.close()


def get_evidence(rule_sn, workshop):
    """Return evidence metadata list for a rule + workshop (no BLOB data)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, rule_sn, workshop, filename, mime_type,
                      thumbnail, created_at
               FROM tqc__evidence
               WHERE rule_sn = ? AND workshop = ?""",
            (rule_sn, workshop)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_evidence_data(evidence_id):
    """Return the full evidence record (including BLOB data) by id."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM tqc__evidence WHERE id = ?",
            (evidence_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def progress_stats(workshop):
    """Return aggregate scoring progress for a single workshop.

    Returns a dict with:
        scored_count   — number of score rows with a non-null score
        total_items    — total number of rules (checklist items)
        scored_points  — sum of actual scores given
        total_points   — sum of max_score for all scored rows
    """
    conn = get_conn()
    try:
        total_items = conn.execute(
            "SELECT COUNT(*) AS cnt FROM tqc__rules"
        ).fetchone()["cnt"]
        scored_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM tqc__scores WHERE workshop = ? AND score IS NOT NULL",
            (workshop,)
        ).fetchone()["cnt"]
        scored_points = conn.execute(
            "SELECT COALESCE(SUM(score), 0) AS total FROM tqc__scores WHERE workshop = ?",
            (workshop,)
        ).fetchone()["total"]
        total_points = conn.execute(
            "SELECT COALESCE(SUM(max_score), 0) AS total FROM tqc__rules"
        ).fetchone()["total"]
        return {
            "scored_count":   scored_count,
            "total_items":    total_items,
            "scored_points":  scored_points,
            "total_points":   total_points,
        }
    finally:
        conn.close()
