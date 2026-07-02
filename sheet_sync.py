#!/usr/bin/env python3
"""TQC Google Sheets sync -- import rules from Sheets, export scores back.

Key constants:
  SHEET_ID         -- Google Sheets spreadsheet ID
  QUARTERLY_SHEET  -- quarterly TQC inspection rule sheet name
  MONTHLY_SHEET    -- monthly TQC inspection rule sheet name

Functions:
  get_gs_service()            -- singleton Google Sheets service (service account)
  read_sheet(sheet_name, ...)  -- read a sheet range, returns list of row lists
  parse_quarterly_rows(rows)   -- parse raw rows into structured rule dicts
  sync_rules_to_db()           -- import quarterly rules into tqc__rules table
  write_scores_to_sheet(ws)    -- write confirmed scores back to column I
"""

import os
import sys

# Local gsheets_auth (copied from scripts/), with env-var support for Render
from gsheets_auth import get_service as _get_gs_base, read_sheet as _read_sheet_base

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SHEET_ID = "1bQYHd5T5yf0g5ILF6aUGmddl-nTKXRwFuotnO-PEYEw"
QUARTERLY_SHEET = "2026 Q2 Quarterly TQC"
MONTHLY_SHEET = "2026 Q2 Monthly TQC"

# ---------------------------------------------------------------------------
# Singleton service
# ---------------------------------------------------------------------------
_service = None


def get_gs_service():
    """Return a singleton Google Sheets service object (service account auth)."""
    global _service
    if _service is None:
        _service = _get_gs_base()
    return _service


# ---------------------------------------------------------------------------
# Sheet I/O
# ---------------------------------------------------------------------------

def read_sheet(sheet_name, range_spec=None):
    """Read a sheet range.  Returns a list of row lists (each row is list of str).

    Parameters
    ----------
    sheet_name : str
        The tab / sheet name (e.g. "2026 Q2 Quarterly TQC").
    range_spec : str | None
        Optional A1 range within the sheet (e.g. "A1:K200").  When omitted the
        entire used range of the sheet is returned.
    """
    service = get_gs_service()
    range_name = sheet_name if range_spec is None else f"{sheet_name}!{range_spec}"
    try:
        return _read_sheet_base(service, SHEET_ID, range_name)
    except Exception as e:
        rng = range_spec or "all"
        raise RuntimeError(
            f"Failed to read sheet '{sheet_name}' (range: {rng}): {e}"
        ) from e


# ---------------------------------------------------------------------------
# Parsing -- quarterly sheet
# ---------------------------------------------------------------------------
# Quarterly sheet column layout (0-indexed):
#   0  检查方式     inspection_way       ← carries down (merged cells)
#   1  考核模块     module               ← carries down (merged cells)
#   2  考核分数     module_score         ← carries down (merged cells)
#   3  序号         sn                   ← skip row if empty
#   4  检查项目     item_name            ← skip row if empty
#   5  标准细则     specs
#   6  评分说明     rating_explanation
#   7  满分         full_score
#   8  实际得分     (ignored on import)
#   9  备注         (ignored on import)
#  10  更新说明     update_summary

def parse_quarterly_rows(rows, sheet_name=None):
    """Parse quarterly TQC sheet rows into structured rule dicts.

    Handles merged-cell carry-down for columns 0 (way), 1 (module),
    and 2 (module_score).  Skips rows where *sn* or *item_name* is empty
    (including the header row).  Assigns incrementing *sort_order*.

    Returns a list of dicts with keys matching the tqc__rules columns:
        sn, category, inspection_item, inspection_way,
        inspection_standard, max_score, sort_order, sheet_name
    """
    rules = []
    last_way = ""
    last_way_zh = ""
    last_module = ""
    last_module_zh = ""
    last_module_score = ""
    sort_order = 0

    for row in rows:
        # Pad short rows so indexing never raises
        while len(row) < 11:
            row.append("")

        # Helper: extract English part from bilingual cells (中文\n English)
        def _en(s):
            parts = [(p or "").strip() for p in (s or "").split("\n")]
            parts = [p for p in parts if p]  # drop empties
            if len(parts) >= 2 and parts[-1].startswith("（"):
                return parts[-2]  # skip the parenthetical category suffix
            result = parts[-1] if len(parts) > 1 else (parts[0] if parts else "")
            # If result has CJK mixed with ASCII on one line, extract English portion
            cjk = sum(1 for c in result if '一' <= c <= '鿿')
            if cjk > 0 and len(result) > cjk:
                import re as _re
                segments = _re.split(r'[一-鿿]+', result)
                en = ' '.join(s.strip() for s in segments if s.strip())
                if en:
                    return en
            return result

        # Helper: extract Chinese part from bilingual cells (中文\n English)
        def _zh(s):
            parts = [(p or "").strip() for p in (s or "").split("\n")]
            parts = [p for p in parts if p]  # drop empties
            if not parts:
                return ""
            # First non-parenthetical part is usually Chinese
            for p in parts:
                if p.startswith("（"):
                    continue
                cjk = sum(1 for c in p if '一' <= c <= '鿿')
                if cjk > 0:
                    return p
            return parts[0]  # fallback

        # Helper: extract English-only paragraphs from bilingual long text.
        # Handles two patterns:
        #   1. Chinese block, blank line(s), English block (split by paragraph)
        #   2. Chinese and English interleaved line-by-line
        # Strategy: split into lines, drop any line with significant CJK content,
        # then join remaining English lines back together.
        def _extract_en(text):
            if not text:
                return ""
            lines = text.split("\n")
            en_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    # Blank lines: keep as paragraph separators, but only if
                    # we already have English content accumulated.
                    if en_lines and en_lines[-1] != "":
                        en_lines.append("")
                    continue
                # Count CJK (Chinese/Japanese/Korean) characters in this line
                cjk = sum(1 for c in stripped
                          if ('一' <= c <= '鿿' or   # CJK Unified
                              '㐀' <= c <= '䶿' or   # CJK Ext-A
                              '豈' <= c <= '﫿' or   # CJK Compat
                              '぀' <= c <= 'ヿ'))     # Hiragana/Katakana
                total = sum(1 for c in stripped if not c.isspace())
                if total == 0:
                    continue
                # Drop line if >15% CJK characters
                if cjk / total <= 0.15:
                    en_lines.append(stripped)
            # Clean up trailing/leading blank lines
            while en_lines and en_lines[0] == "":
                en_lines.pop(0)
            while en_lines and en_lines[-1] == "":
                en_lines.pop()
            return "\n".join(en_lines)

        # Helper: extract Chinese-only paragraphs from bilingual long text.
        # Mirror of _extract_en — keeps lines with >15% CJK characters.
        def _extract_zh(text):
            if not text:
                return ""
            lines = text.split("\n")
            zh_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    if zh_lines and zh_lines[-1] != "":
                        zh_lines.append("")
                    continue
                cjk = sum(1 for c in stripped
                          if ('一' <= c <= '鿿' or '㐀' <= c <= '䶿' or
                              '豈' <= c <= '﫿' or '぀' <= c <= 'ヿ'))
                total = sum(1 for c in stripped if not c.isspace())
                if total == 0:
                    continue
                if cjk / total > 0.15:
                    zh_lines.append(stripped)
            while zh_lines and zh_lines[0] == "":
                zh_lines.pop(0)
            while zh_lines and zh_lines[-1] == "":
                zh_lines.pop()
            return "\n".join(zh_lines)

        way = _en(row[0])
        way_zh = _zh(row[0])
        module = _en(row[1])
        module_zh = _zh(row[1])
        module_score = _en(row[2])
        sn = _en(row[3])
        item_name = _en(row[4])
        item_name_zh = _zh(row[4])
        specs = _extract_en(row[5] or "")
        specs_zh = _extract_zh(row[5] or "")
        rating_explanation = _extract_en(row[6] or "")
        full_score = (row[7] or "").strip()

        # --- carry-down for merged cells ---
        if way:
            last_way = way
        if way_zh:
            last_way_zh = way_zh
        if module:
            last_module = module
        if module_zh:
            last_module_zh = module_zh
        if module_score:
            last_module_score = module_score

        # --- skip header / empty rows ---
        if not sn or not item_name:
            continue

        if sn in ("序号", "SN") or item_name in ("检查项目", "Inspection Item"):
            continue

        # --- full_score: coerce to int, default 100 ---
        try:
            max_score = int(full_score) if full_score else 100
        except ValueError:
            max_score = 100

        # --- inspection_standard: specs only (rating_explanation stored separately) ---
        inspection_standard = specs

        sort_order += 1

        rules.append({
            "sn": sn,
            "category": last_module,
            "category_zh": last_module_zh,
            "inspection_item": item_name,
            "inspection_item_zh": item_name_zh,
            "inspection_way": last_way,
            "inspection_way_zh": last_way_zh,
            "inspection_standard": inspection_standard,
            "inspection_standard_zh": specs_zh,
            "rating_explanation": rating_explanation,
            "max_score": max_score,
            "sort_order": sort_order,
            "sheet_name": sheet_name or QUARTERLY_SHEET,
        })

    return rules


# ---------------------------------------------------------------------------
# Import -- rules into tqc__rules
# ---------------------------------------------------------------------------

def sync_rules_to_db(quarter=None):
    """Read the quarterly sheet, parse rows, and upsert into **tqc__rules**.

    If *quarter* is given (e.g. '2026 Q2'), reads that quarter's sheet.
    Otherwise uses the default QUARTERLY_SHEET.
    """
    import db  # same-directory module

    sheet = f"{quarter} Quarterly TQC" if quarter else QUARTERLY_SHEET
    rows = read_sheet(sheet)
    rules = parse_quarterly_rows(rows, sheet)

    if not rules:
        print("No rules parsed from sheet -- nothing to sync.")
        return

    conn = db.get_conn()
    inserted = 0
    updated = 0

    try:
        # Fetch all existing (sn, sheet_name) pairs in one query instead of
        # N individual SELECTs inside the loop.
        existing_pairs = {
            (row[0], row[1])
            for row in conn.execute("SELECT sn, sheet_name FROM tqc__rules")
        }

        for rule in rules:
            if (rule["sn"], rule["sheet_name"]) in existing_pairs:
                conn.execute(
                    """
                    UPDATE tqc__rules SET
                        category = ?,
                        category_zh = ?,
                        inspection_item = ?,
                        inspection_item_zh = ?,
                        inspection_way = ?,
                        inspection_way_zh = ?,
                        inspection_standard = ?,
                        inspection_standard_zh = ?,
                        rating_explanation = ?,
                        max_score = ?,
                        sort_order = ?,
                        updated_at = datetime('now')
                    WHERE sn = ? AND sheet_name = ?
                    """,
                    (
                        rule["category"],
                        rule.get("category_zh", ""),
                        rule["inspection_item"],
                        rule.get("inspection_item_zh", ""),
                        rule["inspection_way"],
                        rule.get("inspection_way_zh", ""),
                        rule["inspection_standard"],
                        rule.get("inspection_standard_zh", ""),
                        rule.get("rating_explanation", ""),
                        rule["max_score"],
                        rule["sort_order"],
                        rule["sn"],
                        rule["sheet_name"],
                    ),
                )
                updated += 1
            else:
                conn.execute(
                    """
                    INSERT INTO tqc__rules
                        (sn, category, category_zh, inspection_item, inspection_item_zh,
                         inspection_way, inspection_way_zh,
                         inspection_standard, inspection_standard_zh,
                         rating_explanation,
                         max_score, sort_order, sheet_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rule["sn"],
                        rule["category"],
                        rule.get("category_zh", ""),
                        rule["inspection_item"],
                        rule.get("inspection_item_zh", ""),
                        rule["inspection_way"],
                        rule.get("inspection_way_zh", ""),
                        rule["inspection_standard"],
                        rule.get("inspection_standard_zh", ""),
                        rule.get("rating_explanation", ""),
                        rule["max_score"],
                        rule["sort_order"],
                        rule["sheet_name"],
                    ),
                )
                inserted += 1

        conn.commit()
        print(f"Rules synced: {inserted} inserted, {updated} updated")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Export -- scores back to the sheet
# ---------------------------------------------------------------------------

def write_scores_to_sheet(workshop):
    """Write confirmed scores back to column I (实际得分) in the quarterly sheet.

    Steps
    -----
    1. Read the current sheet to build an SN → row-number map.
    2. Query ``tqc__scores`` for confirmed scores of *workshop*.
    3. For each confirmed score, update ``{sheet}!I{row}`` via the Sheets API.

    Parameters
    ----------
    workshop : str
        Workshop name (e.g. "Montevideo") matching the *workshop* column in
        ``tqc__scores``.
    """
    import db

    # 1.  Read sheet, map SN → 1-indexed row number
    rows = read_sheet(QUARTERLY_SHEET)
    sn_to_row = {}
    for i, row in enumerate(rows):
        if len(row) > 3:
            sn = (row[3] or "").strip()
            if sn:
                sn_to_row[sn] = i + 1  # Sheets API rows are 1-indexed

    # 2.  Query confirmed scores
    all_scores = db.scores_for_workshop(workshop)
    confirmed = {
        sn: s
        for sn, s in all_scores.items()
        if s.get("confirmed") and s.get("score") is not None
    }

    if not confirmed:
        print(f"No confirmed scores found for workshop '{workshop}'.")
        return

    # 3.  Write all scores in a single batchUpdate call instead of N individual
    #     values().update() calls.
    service = get_gs_service()
    data = []

    for sn, sd in confirmed.items():
        row_num = sn_to_row.get(sn)
        if row_num is None:
            print(f"  Warning: SN '{sn}' not found in sheet, skipping.")
            continue

        data.append({
            "range": f"{QUARTERLY_SHEET}!I{row_num}",
            "values": [[sd["score"]]],
        })

    if not data:
        print(f"No confirmed scores with matching rows for workshop '{workshop}'.")
        return

    body = {
        "valueInputOption": "USER_ENTERED",
        "data": data,
    }
    try:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=SHEET_ID, body=body
        ).execute()
    except Exception as e:
        raise RuntimeError(
            f"Failed to write scores for workshop '{workshop}': {e}"
        ) from e

    print(
        f"Scores written: {len(data)} rows updated for workshop '{workshop}'."
    )
