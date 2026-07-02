"""
tqc/evidence_store -- Photo/document evidence storage as SQLite BLOBs
with automatic thumbnail generation.

Stores files up to 2 MB; attempts JPEG compression for oversized images.
Generates 200 px thumbnails for all image types.
"""

import io
import json

from PIL import Image

from db import get_conn

MAX_SIZE = 2 * 1024 * 1024   # 2 MB
THUMB_SIZE = (200, 200)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_thumbnail(data):
    """Return a 200 px JPEG thumbnail of *data* as bytes, or *None* on failure."""
    try:
        img = Image.open(io.BytesIO(data))
        img.thumbnail(THUMB_SIZE)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return buf.getvalue()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_evidence(rule_sn, workshop, filename, data, mime_type, quarter=None):
    """Persist evidence as a BLOB, optionally generating a thumbnail.

    If *data* exceeds **MAX_SIZE** (2 MB) and *mime_type* indicates an
    image, the function attempts to re-compress the image as RGB JPEG at
    quality 60.  When this still does not bring the size below the limit
    (or the file is not an image), a :class:`ValueError` is raised.

    Parameters
    ----------
    rule_sn : str
        Rule serial number this evidence belongs to.
    workshop : str
        Workshop name.
    filename : str
        Original file name (stored in ``filename``).
    data : bytes
        Raw file bytes.
    mime_type : str
        MIME type string (e.g. ``"image/jpeg"``).

    Returns
    -------
    int
        The newly inserted evidence row ID.

    Raises
    ------
    ValueError
        If *data* is larger than 2 MB and cannot be compressed.
    """
    is_image = bool(mime_type and mime_type.startswith("image/"))

    # -- compress oversized images ------------------------------------------
    if len(data) > MAX_SIZE:
        if not is_image:
            raise ValueError(
                f"Evidence data size ({len(data)} bytes) exceeds "
                f"maximum allowed size ({MAX_SIZE} bytes)"
            )
        try:
            img = Image.open(io.BytesIO(data))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60)
            data = buf.getvalue()
        except Exception:
            raise ValueError(
                f"Evidence data size ({len(data)} bytes) exceeds "
                f"maximum allowed size ({MAX_SIZE} bytes) and "
                f"could not be compressed"
            )

    # -- final size guard ---------------------------------------------------
    if len(data) > MAX_SIZE:
        raise ValueError(
            f"Evidence data size ({len(data)} bytes) exceeds "
            f"maximum allowed size ({MAX_SIZE} bytes) even after compression"
        )

    # -- thumbnail ----------------------------------------------------------
    thumbnail = None
    if is_image:
        thumbnail = _generate_thumbnail(data)

    # -- persist ------------------------------------------------------------
    conn = get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO tqc__evidence
               (rule_sn, workshop, filename, mime_type, data, thumbnail, quarter)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (rule_sn, workshop, filename, mime_type, data, thumbnail, quarter),
        )
        evidence_id = cursor.lastrowid

        # Append the new ID to the JSON array in tqc__scores
        row = conn.execute(
            "SELECT evidence_ids FROM tqc__scores WHERE rule_sn = ? AND workshop = ?",
            (rule_sn, workshop),
        ).fetchone()

        ids = json.loads(row["evidence_ids"]) if row and row["evidence_ids"] else []
        ids.append(evidence_id)

        conn.execute(
            """INSERT INTO tqc__scores (rule_sn, workshop, evidence_ids)
               VALUES (?, ?, ?)
               ON CONFLICT(rule_sn, workshop) DO UPDATE SET
                   evidence_ids = excluded.evidence_ids""",
            (rule_sn, workshop, json.dumps(ids)),
        )

        conn.commit()
        return evidence_id
    finally:
        conn.close()


def delete_evidence(evidence_id):
    """Delete an evidence record and remove its ID from ``tqc__scores.evidence_ids``.

    Parameters
    ----------
    evidence_id : int
        The evidence row ID to delete.
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT rule_sn, workshop FROM tqc__evidence WHERE id = ?",
            (evidence_id,),
        ).fetchone()

        if row is None:
            return

        rule_sn = row["rule_sn"]
        workshop = row["workshop"]

        conn.execute("DELETE FROM tqc__evidence WHERE id = ?", (evidence_id,))

        # Remove the deleted ID from the scores JSON array
        score_row = conn.execute(
            "SELECT evidence_ids FROM tqc__scores WHERE rule_sn = ? AND workshop = ?",
            (rule_sn, workshop),
        ).fetchone()

        if score_row and score_row["evidence_ids"]:
            ids = json.loads(score_row["evidence_ids"])
            ids = [i for i in ids if i != evidence_id]
            conn.execute(
                "UPDATE tqc__scores SET evidence_ids = ? WHERE rule_sn = ? AND workshop = ?",
                (json.dumps(ids), rule_sn, workshop),
            )

        conn.commit()
    finally:
        conn.close()
