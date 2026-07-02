"""
tqc/rule_engine — Auto-score computable inspection items from uruguay.db data.

Parses scoring rules and auto-scores computable inspection items by querying
existing data in uruguay.db.  Uses sqlite3 directly (not the db module's
connection helper) to keep this module importable without side effects.
"""

import os
import re
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uruguay.db")

# ---------------------------------------------------------------------------
# Threshold parsing
# ---------------------------------------------------------------------------

def parse_thresholds(rating_text: str) -> "list[tuple[int, int, int]]":
    """Parse threshold-based scoring rules from Chinese+English text.

    Supported patterns (order-independent):
        ">=90% -> 40pts" or  ">=90%->40pts"  or  ">=90%得40分"
           ->  (90, 101, 40)   (max=101 so values up to 100.0 pass)
        "[75%,90%) -> 30pts"  or  "[75%, 90%)->30pts"
           ->  (75, 90, 30)    (exclusive upper bound via strict <)
        "[60%,75%) -> 20pts"
           ->  (60, 75, 20)
        "<60% -> 0pts"  or  "<60%->0pts"
           ->  (0, 60, 0)      (exclusive upper bound via strict <)

    Returns a list of (min_pct, max_pct, score) sorted by score descending.
    """
    thresholds: "list[tuple[int, int, int]]" = []

    # --- Pattern A:  ">=X%"  (greater-than-or-equal)
    for m in re.finditer(
        r'(?:>=|≥|＞=?)\s*(\d+(?:\.\d+)?)\s*%\s*(?:→|->|=>|得|:)\s*(\d+)\s*(?:pts|分)?',
        rating_text,
    ):
        lo = int(float(m.group(1)))
        score = int(m.group(2))
        thresholds.append((lo, 101, score))  # 101 so 100.0 < 101 passes

    # --- Pattern B:  "[X%, Y%)"  interval notation (exclusive upper)
    for m in re.finditer(
        r'\[\s*(\d+(?:\.\d+)?)\s*%\s*,\s*(\d+(?:\.\d+)?)\s*%\s*\)'
        r'\s*(?:→|->|=>|得|:)\s*(\d+)\s*(?:pts|分)?',
        rating_text,
    ):
        lo = int(float(m.group(1)))
        hi = int(float(m.group(2)))  # raw upper bound; strict < in apply_threshold
        score = int(m.group(3))
        thresholds.append((lo, hi, score))

    # --- Pattern C:  "<X%"  (strictly less-than)
    for m in re.finditer(
        r'(?:<|≤|＜)\s*(\d+(?:\.\d+)?)\s*%\s*(?:→|->|=>|得|:)\s*(\d+)\s*(?:pts|分)?',
        rating_text,
    ):
        hi = int(float(m.group(1)))  # raw upper bound; strict < in apply_threshold
        score = int(m.group(2))
        thresholds.append((0, hi, score))

    # Descending by score
    thresholds.sort(key=lambda t: t[2], reverse=True)
    return thresholds


def apply_threshold(value_pct: float, thresholds: "list[tuple[int, int, int]]") -> int:
    """Return the matching score for *value_pct* (0-100).

    Uses ``min_pct <= value_pct < max_pct`` (exclusive upper bound).
    For ">=X" patterns max_pct is stored as 101 so values up to 100.0 pass.

    Returns 0 if no threshold bracket matches.
    """
    for min_pct, max_pct, score in thresholds:
        if min_pct <= value_pct < max_pct:
            return score
    return 0


# ---------------------------------------------------------------------------
# Auto-scoring logic
# ---------------------------------------------------------------------------

def auto_score_item(sn: str, rules_dict: dict, conn: "sqlite3.Connection | None" = None) -> "tuple[int | None, str]":
    """Attempt to auto-score one inspection item.

    Parameters
    ----------
    sn : str
        Rule serial number (e.g. "A-1-2").
    rules_dict : dict
        All rules keyed by SN.  Each value is a dict with at least the keys
        returned by ``db.all_rules()``: ``sn``, ``inspection_item``,
        ``max_score``, ``inspection_standard``, ``inspection_way``, etc.
    conn : sqlite3.Connection or None
        Optional existing database connection.  If None, a new connection is
        opened and closed within this call.

    Returns
    -------
    (score, reason)  or  (None, reason_if_cannot_score)
    """
    rule = rules_dict.get(sn)
    if rule is None:
        return (None, f"Rule {sn} not found in rules_dict")

    item_name = rule.get("inspection_item", "")
    full_score = int(rule.get("max_score", 100))
    rating_text = rule.get("inspection_standard") or ""

    own_conn = conn is None
    if own_conn:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    try:
        # ---- A-1-4  or  name contains "技术问诊" ----
        if sn == "A-1-4" or "技术问诊" in item_name:
            count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM tis__inquiry"
            ).fetchone()["cnt"]
            if count > 0:
                return (full_score, f"tis__inquiry: {count} rows found")
            else:
                return (0, f"tis__inquiry: no data")

        # ---- name contains "Cloud" or "激活" ----
        if "Cloud" in item_name or "激活" in item_name:
            total = conn.execute(
                "SELECT COUNT(*) AS cnt FROM crm__cloud"
            ).fetchone()["cnt"]
            activated = conn.execute(
                "SELECT COUNT(*) AS cnt FROM crm__cloud WHERE cloud_status = 'Y'"
            ).fetchone()["cnt"]
            if total == 0:
                return (None, "crm__cloud: no data")
            pct = (activated / total) * 100
            thresholds = parse_thresholds(rating_text)
            score = apply_threshold(pct, thresholds) if thresholds else 0
            return (
                score,
                f"crm__cloud: {activated}/{total} activated ({pct:.1f}%)",
            )

        # ---- name contains "Promoter" or "NPS转化" ----
        if "Promoter" in item_name or "NPS转化" in item_name:
            total = conn.execute(
                "SELECT COUNT(*) AS cnt FROM nps__raw"
            ).fetchone()["cnt"]
            promoters = conn.execute(
                "SELECT COUNT(*) AS cnt FROM nps__raw WHERE nps_category = 'Promoter'"
            ).fetchone()["cnt"]
            if total == 0:
                return (None, "nps__raw: no data")
            pct = (promoters / total) * 100
            thresholds = parse_thresholds(rating_text)
            score = apply_threshold(pct, thresholds) if thresholds else 0
            return (
                score,
                f"nps__raw: {promoters}/{total} Promoters ({pct:.1f}%)",
            )

        # ---- name contains "1DC" ----
        if "1DC" in item_name:
            count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM nps__one_dc"
            ).fetchone()["cnt"]
            if count > 0:
                return (full_score, f"nps__one_dc: {count} rows found")
            else:
                return (0, f"nps__one_dc: no data")

        # ---- A-1-2  or  name contains "DMS工单" ----
        if sn == "A-1-2" or "DMS工单" in item_name:
            total = conn.execute(
                "SELECT COUNT(*) AS cnt FROM wo__raw"
            ).fetchone()["cnt"]
            # "Complete" means all key fields non-null and non-empty:
            #   vin, workshop, mileage, wo_type,
            #   service_date (open_date), service_finished (close_date),
            #   labour_hour (labor_hour), labour_amount (total_amount)
            complete = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM wo__raw
                WHERE vin          IS NOT NULL AND vin          != ''
                  AND workshop     IS NOT NULL AND workshop     != ''
                  AND mileage      IS NOT NULL
                  AND wo_type      IS NOT NULL AND wo_type      != ''
                  AND service_date IS NOT NULL AND service_date != ''
                  AND service_finished IS NOT NULL AND service_finished != ''
                  AND labour_hour  IS NOT NULL
                  AND labour_amount IS NOT NULL
                """
            ).fetchone()["cnt"]
            if total == 0:
                return (None, "wo__raw: no data")
            pct = (complete / total) * 100
            thresholds = parse_thresholds(rating_text)
            score = apply_threshold(pct, thresholds) if thresholds else 0
            return (
                score,
                f"wo__raw: {complete}/{total} complete ({pct:.1f}%)",
            )

        # ---- no matching rule ----
        return (
            None,
            f"No auto-score rule matches SN={sn}, item='{item_name}'",
        )
    finally:
        if own_conn:
            conn.close()


# ---------------------------------------------------------------------------
# Batch run
# ---------------------------------------------------------------------------

def run_auto_scoring(workshop: str) -> int:
    """Run auto_score_item for ALL rules and persist results via db.upsert_score().

    Only sets ``auto_score`` (and ``score`` for convenience); leaves
    ``confirmed`` = 0 so that human review is still required.

    Opens a single database connection and reuses it for all items
    (avoids N+1 connections).

    Returns the number of items that were auto-scored (score not None).
    """
    # Late import to avoid circular dependency at module level.
    from db import all_rules, upsert_score

    rules = all_rules()
    rules_dict = {r["sn"]: r for r in rules}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        count = 0
        for rule in rules:
            sn = rule["sn"]
            score, reason = auto_score_item(sn, rules_dict, conn=conn)
            if score is not None:
                upsert_score(
                    rule_sn=sn,
                    workshop=workshop,
                    score=score,
                    max_score=rule.get("max_score", 100),
                    auto_score=score,
                    auto_reason=reason,
                    confirmed=0,
                    remarks=None,
                )
                count += 1

        return count
    finally:
        conn.close()
