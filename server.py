"""
tqc/server — Flask web application for the TQC scoring tool.

Routes:
  /                       Main checklist
  /item/<sn>              Item detail
  /review                 Review summary
  /export                 Export page
  /api/confirm            Confirm a single score
  /api/confirm-batch      Confirm all auto-scores for a workshop
  /api/upload             Upload evidence photo
  /api/evidence/<id>      Serve full evidence image
  /api/evidence/<id>/thumb Serve evidence thumbnail
  /api/evidence/<id>/delete Delete evidence
  /api/sync-rules         Sync rules from Google Sheets
  /api/auto-score         Run auto-scoring for a workshop
  /api/write-scores       Write confirmed scores to Google Sheets
"""

from flask import Flask, render_template, request, jsonify, send_file, g
from io import BytesIO

from db import (
    init_db, all_rules, rules_by_way, scores_for_workshop,
    upsert_score, get_evidence, get_evidence_data, progress_stats, get_conn,
)
from rule_engine import run_auto_scoring
from evidence_store import save_evidence, delete_evidence
from sheet_sync import sync_rules_to_db, write_scores_to_sheet

import os
app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))

WORKSHOPS = ["Warehouse", "ODL", "AMAYA", "PORTONES"]
QUARTERS = ["2026 Q1", "2026 Q2", "2026 Q3", "2026 Q4"]
COUNTRIES = ["Uruguay", "Paraguay", "Bolivia"]
LANGS = {"en": "English", "zh": "中文", "es": "Español"}

from db import COUNTRY_DB, DEFAULT_DB
from translations import T as TRANSLATIONS


def _(key, *args):
    """Translate key to current language. Usage: _('score') or _('max_pts', 100)."""
    lang = g.get("lang", "en")
    text = TRANSLATIONS.get(lang, {}).get(key, TRANSLATIONS["en"].get(key, key))
    if args:
        return text.format(*args)
    return text


@app.before_request
def set_country_db():
    country = request.args.get("country", "Uruguay")
    if country not in COUNTRY_DB:
        country = "Uruguay"
    g.db_path = COUNTRY_DB.get(country, DEFAULT_DB)
    g.country = country
    g.lang = request.args.get("lang", "en")
    if g.lang not in LANGS:
        g.lang = "en"


@app.context_processor
def inject_nav_counts():
    """Provide pending counts and translation helper for templates."""
    pending = 0
    try:
        conn = get_conn()
        pending = conn.execute(
            "SELECT COUNT(*) FROM tqc__rules r WHERE NOT EXISTS "
            "(SELECT 1 FROM tqc__scores s WHERE s.rule_sn = r.sn AND s.score IS NOT NULL)"
        ).fetchone()[0]
        conn.close()
    except Exception:
        pass
    def t(rule, field):
        """Return the language-appropriate translation of a rule field."""
        lang = g.get("lang", "en")
        if lang == "en":
            return rule.get(field, "")
        val = rule.get(f"{field}_{lang}", "")
        return val if val else rule.get(field, "")

    return {"nav_pending": pending, "_": _, "langs": LANGS, "t": t}


def _validate_workshop(workshop):
    """Return validated workshop name."""
    return (workshop or "").strip()


def _get_quarter():
    """Return validated quarter, defaulting to '2026 Q2'."""
    q = (request.args.get("quarter") or "2026 Q2").strip()
    return q if q in QUARTERS else "2026 Q2"


def _group_by_module(rules):
    """Group a list of rule dicts by their 'category' (module) field."""
    grouped = {}
    for r in rules:
        mod = r.get("category", "Other") or "Other"
        grouped.setdefault(mod, []).append(r)
    return grouped


# ---------------------------------------------------------------------------
# HTML Page Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Main checklist page — or country selector landing."""
    country = request.args.get("country", "")
    if not country:
        return render_template("landing.html", countries=COUNTRIES)
    workshop = _validate_workshop(request.args.get("workshop"))
    quarter = _get_quarter()

    online_rules = rules_by_way("Online", quarter)
    onsite_rules = rules_by_way("On-site", quarter)
    scores = scores_for_workshop(workshop)

    # Merge scores into rules (look up by SN)
    def merge(rule_list):
        result = []
        for r in rule_list:
            d = dict(r)
            # Ensure translated fields are present
            d.setdefault("inspection_item_zh", "")
            d.setdefault("inspection_item_es", "")
            d.setdefault("category_zh", "")
            d.setdefault("category_es", "")
            s = scores.get(r["sn"], {})
            d["_score"] = s.get("score")
            d["_max_score"] = s.get("max_score", r.get("max_score", 100))
            d["_auto_score"] = s.get("auto_score")
            d["_auto_reason"] = s.get("auto_reason")
            d["_confirmed"] = s.get("confirmed", 0)
            d["_remarks"] = s.get("remarks")
            d["_evidence_ids"] = s.get("evidence_ids", "[]")
            result.append(d)
        return result

    online_merged = merge(online_rules)
    onsite_merged = merge(onsite_rules)

    online_modules = _group_by_module(online_merged)
    onsite_modules = _group_by_module(onsite_merged)

    stats = progress_stats(workshop)

    return render_template(
        "index.html",
        workshop=workshop,
        quarter=quarter,
        country=g.country,
        countries=COUNTRIES,
        workshops=WORKSHOPS,
        quarters=QUARTERS,
        online_modules=online_modules,
        onsite_modules=onsite_modules,
        stats=stats,
    )


@app.route("/item/<sn>")
def item_detail(sn):
    """Item detail page."""
    workshop = _validate_workshop(request.args.get("workshop"))
    quarter = _get_quarter()

    # Get rule by SN from tqc__rules
    all_rules_list = all_rules(quarter)
    rules_by_sn = {r["sn"]: r for r in all_rules_list}
    rule = rules_by_sn.get(sn)
    if rule is None:
        return "Item not found", 404

    # Get score for (sn, workshop)
    scores = scores_for_workshop(workshop)
    score = scores.get(sn, {})

    # Get evidence list for (sn, workshop)
    evidence = get_evidence(sn, workshop)

    # Compute prev/next SN for quick navigation
    all_sns = [r["sn"] for r in all_rules_list]
    try:
        idx = all_sns.index(sn)
    except ValueError:
        idx = -1
    prev_sn = all_sns[idx - 1] if idx > 0 else None
    next_sn = all_sns[idx + 1] if idx >= 0 and idx + 1 < len(all_sns) else None

    return render_template(
        "item.html",
        rule=rule,
        score=score,
        evidence=evidence,
        workshop=workshop,
        quarter=quarter,
        prev_sn=prev_sn,
        next_sn=next_sn,
        country=g.country,
        countries=COUNTRIES,
        workshops=WORKSHOPS,
        quarters=QUARTERS,
    )


@app.route("/review")
def review():
    """Review summary page."""
    workshop = _validate_workshop(request.args.get("workshop"))
    quarter = _get_quarter()
    status_filter = request.args.get("filter", "all")

    rules = all_rules(quarter)
    scores = scores_for_workshop(workshop)

    # Build items with status classification
    counts = {"auto": 0, "confirmed": 0, "pending": 0, "manual": 0}
    items = []

    for r in rules:
        s = scores.get(r["sn"], {})
        auto_score = s.get("auto_score")
        confirmed = s.get("confirmed", 0)
        score_val = s.get("score")

        # Determine status:
        #   "auto"      — has auto_score, not confirmed
        #   "confirmed" — confirmed=1
        #   "pending"   — no auto_score, not confirmed, score==0
        #   "manual"    — otherwise
        if auto_score is not None and not confirmed:
            status = "auto"
        elif confirmed:
            status = "confirmed"
        elif auto_score is None and not confirmed and (score_val or 0) == 0:
            status = "pending"
        else:
            status = "manual"

        counts[status] += 1

        if status_filter != "all" and status != status_filter:
            continue

        items.append({
            "sn": r["sn"],
            "inspection_item": r["inspection_item"],
            "inspection_item_zh": r.get("inspection_item_zh", ""),
            "inspection_item_es": r.get("inspection_item_es", ""),
            "inspection_way": r["inspection_way"],
            "category": r.get("category", ""),
            "category_zh": r.get("category_zh", ""),
            "category_es": r.get("category_es", ""),
            "max_score": r.get("max_score", 100),
            "score": score_val,
            "auto_score": auto_score,
            "auto_reason": s.get("auto_reason"),
            "confirmed": confirmed,
            "remarks": s.get("remarks"),
            "status": status,
        })

    return render_template(
        "review.html",
        workshop=workshop,
        quarter=quarter,
        country=g.country,
        countries=COUNTRIES,
        workshops=WORKSHOPS,
        quarters=QUARTERS,
        items=items,
        filter=status_filter,
        auto_count=counts["auto"],
        confirmed_count=counts["confirmed"],
        manual_count=counts["manual"],
        pending_count=counts["pending"],
    )


@app.route("/export")
def export():
    """Export page."""
    workshop = _validate_workshop(request.args.get("workshop"))
    quarter = _get_quarter()

    rules = all_rules(quarter)
    scores = scores_for_workshop(workshop)
    stats = progress_stats(workshop)

    # Merge scores into rules
    merged = []
    for r in rules:
        d = dict(r)
        s = scores.get(r["sn"], {})
        d["_score"] = s.get("score")
        d["_auto_score"] = s.get("auto_score")
        d["_confirmed"] = s.get("confirmed", 0)
        merged.append(d)

    # Group by module
    modules = _group_by_module(merged)

    # Build module-level summaries
    module_summaries = []
    for mod_name, mod_rules in modules.items():
        scored = sum(1 for r in mod_rules if r["_score"] is not None)
        total = len(mod_rules)
        points = sum(r["_score"] or 0 for r in mod_rules)
        max_points = sum(r.get("max_score", 100) for r in mod_rules)
        module_summaries.append({
            "name": mod_name,
            "scored": scored,
            "total": total,
            "points": points,
            "max_points": max_points,
        })

    return render_template(
        "export.html",
        workshop=workshop,
        quarter=quarter,
        country=g.country,
        countries=COUNTRIES,
        workshops=WORKSHOPS,
        quarters=QUARTERS,
        modules=module_summaries,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# API Endpoints (all return JSON)
# ---------------------------------------------------------------------------

@app.route("/api/confirm", methods=["POST"])
def api_confirm():
    """Confirm a single score. Body: {sn, workshop, score, max_score, auto_score, remarks}."""
    data = request.get_json(silent=True) or {}
    sn = data.get("sn")
    workshop = data.get("workshop")
    score = data.get("score")
    max_score = data.get("max_score", 100)
    auto_score = data.get("auto_score")
    remarks = data.get("remarks")

    if not sn or not workshop:
        return jsonify({"error": "sn and workshop are required"}), 400

    upsert_score(
        rule_sn=sn,
        workshop=workshop,
        score=score,
        max_score=max_score,
        auto_score=auto_score,
        auto_reason=None,
        confirmed=1,
        remarks=remarks,
    )

    return jsonify({"ok": True, "sn": sn, "workshop": workshop})


@app.route("/api/undo-confirm", methods=["POST"])
def api_undo_confirm():
    """Undo score confirmation: set score and confirmed back to null."""
    data = request.get_json(silent=True) or {}
    sn = data.get("sn")
    workshop = data.get("workshop")
    if not sn or not workshop:
        return jsonify({"ok": False, "error": "sn and workshop required"}), 400
    conn = get_conn()
    conn.execute(
        "UPDATE tqc__scores SET score = NULL, confirmed = 0, remarks = NULL WHERE rule_sn = ? AND workshop = ?",
        (sn, workshop)
    )
    conn.commit(); conn.close()
    return jsonify({"ok": True})


@app.route("/api/confirm-batch", methods=["POST"])
def api_confirm_batch():
    """Batch confirm: UPDATE all auto-scored, unconfirmed rows for a workshop."""
    data = request.get_json(silent=True) or {}
    workshop = data.get("workshop")

    if not workshop:
        return jsonify({"error": "workshop is required"}), 400

    conn = get_conn()
    try:
        result = conn.execute(
            """UPDATE tqc__scores
               SET confirmed = 1, updated_at = datetime('now')
               WHERE workshop = ?
                 AND auto_score IS NOT NULL
                 AND confirmed = 0""",
            (workshop,),
        )
        conn.commit()
        updated = result.rowcount
    finally:
        conn.close()

    return jsonify({"ok": True, "updated": updated, "workshop": workshop})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Upload evidence file. Multipart form: file, sn, workshop."""
    sn = request.form.get("sn")
    workshop = request.form.get("workshop")
    quarter = request.form.get("quarter")
    file = request.files.get("file")

    if not sn or not workshop:
        return jsonify({"error": "sn and workshop are required"}), 400
    if not file:
        return jsonify({"error": "file is required"}), 400

    try:
        evidence_id = save_evidence(
            rule_sn=sn,
            workshop=workshop,
            filename=file.filename,
            data=file.read(),
            mime_type=file.mimetype,
            quarter=quarter,
        )
        return jsonify({"ok": True, "evidence_id": evidence_id})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/evidence/<int:eid>")
def api_evidence(eid):
    """Serve full evidence image via send_file."""
    record = get_evidence_data(eid)
    if record is None:
        return jsonify({"error": "Evidence not found"}), 404

    data = record.get("data")
    mime_type = record.get("mime_type", "application/octet-stream")

    if data is None:
        return jsonify({"error": "No data for this evidence"}), 404

    return send_file(BytesIO(data), mimetype=mime_type)


@app.route("/api/evidence/<int:eid>/thumb")
def api_evidence_thumb(eid):
    """Serve evidence thumbnail, fallback to full image."""
    record = get_evidence_data(eid)
    if record is None:
        return jsonify({"error": "Evidence not found"}), 404

    thumb = record.get("thumbnail")
    if thumb:
        return send_file(BytesIO(thumb), mimetype="image/jpeg")

    # Fallback to full image
    data = record.get("data")
    if data is None:
        return jsonify({"error": "No data for this evidence"}), 404

    return send_file(BytesIO(data), mimetype=record.get("mime_type", "image/jpeg"))


@app.route("/api/evidence/<int:eid>/delete", methods=["POST"])
def api_evidence_delete(eid):
    """Delete an evidence record."""
    delete_evidence(eid)
    return jsonify({"ok": True, "deleted": eid})


@app.route("/api/sync-rules", methods=["POST"])
def api_sync_rules():
    """Sync rules from Google Sheets to database. Body: {quarter}."""
    data = request.get_json(silent=True) or {}
    quarter = data.get("quarter")
    try:
        sync_rules_to_db(quarter)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/auto-score", methods=["POST"])
def api_auto_score():
    """Run auto-scoring for a workshop. Body: {workshop}."""
    data = request.get_json(silent=True) or {}
    workshop = data.get("workshop")

    if not workshop:
        return jsonify({"error": "workshop is required"}), 400

    try:
        count = run_auto_scoring(workshop)
        return jsonify({"ok": True, "scored": count, "workshop": workshop})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/write-scores", methods=["POST"])
def api_write_scores():
    """Write confirmed scores to Google Sheets. Body: {workshop}."""
    data = request.get_json(silent=True) or {}
    workshop = data.get("workshop")

    if not workshop:
        return jsonify({"error": "workshop is required"}), 400

    try:
        write_scores_to_sheet(workshop)
        return jsonify({"ok": True, "workshop": workshop})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/db")
def api_db():
    import os, sqlite3
    from db import get_db_path, rules_by_way, _quarter_sheet
    p = get_db_path()
    c = sqlite3.connect(p).execute("SELECT COUNT(*) FROM tqc__rules").fetchone()[0]
    q = _quarter_sheet("2026 Q2")
    online = rules_by_way("Online", "2026 Q2")
    onsite = rules_by_way("On-site", "2026 Q2")
    return {
        "db_path": p, "rules": c, "TQC_DATA_DIR": os.environ.get("TQC_DATA_DIR", "NONE"),
        "quarter_sheet": q,
        "online_count": len(online),
        "onsite_count": len(onsite),
        "sample_online": online[0] if online else None,
    }

# ---------------------------------------------------------------------------
# Startup — initialize database when module loads
# ---------------------------------------------------------------------------
init_db()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print("Starting TQC server on http://localhost:8789", flush=True)
    app.run(host="0.0.0.0", port=8789, debug=True)
