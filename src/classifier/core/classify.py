"""Core per-row classification: the single invariant entry point.

The three field helpers (``normalize_doc_type`` / ``fill_type`` /
``fill_discipline``) live here (relocated from ``pipeline/_row.py``, which now
re-exports them). ``classify_record`` composes them once so every execution
backend shares identical row logic.

Each helper takes ``(existing_value, title)`` and returns ``(value, reason)``.
"""
from __future__ import annotations

from classifier.config.buckets import BUCKET_TO_CLASS, TYPE_TO_BUCKET
from classifier.core.discipline_scoring import pick_discipline_with_overrides
from classifier.core.type_scoring import pick_type_with_overrides
from classifier.core.record import Record, FieldResult, ClassificationResult
from classifier.io.normalize import is_empty

DRAWING_ALIASES = {"drawing", "drawings", "dwg"}
DOCUMENT_ALIASES = {"document", "documents", "doc", "docs"}
SHEET_ALIASES = {"sheet", "sheets"}


def normalize_doc_type(value: str, title: str) -> tuple[str, str]:
    """Return ``(normalized, reason)``. reason: existing / via_keyword / via_override / defaulted."""
    if not is_empty(value):
        v = str(value).strip().lower()
        if v in DRAWING_ALIASES:
            return "drawing", "existing"
        if v in SHEET_ALIASES:
            return "sheet", "existing"
        if v in DOCUMENT_ALIASES:
            return "document", "existing"
    pick = pick_type_with_overrides(title)
    if pick["confidence"] == "high":
        bucket = TYPE_TO_BUCKET.get(pick["type"])
        if bucket is not None:
            folded = BUCKET_TO_CLASS[bucket]
            reason_tag = "via_override" if pick["reason"] == "override" else "via_keyword"
            cls = {"Drawings": "drawing", "Sheets": "sheet"}.get(folded, "document")
            return cls, reason_tag
    return "document", "defaulted"


def fill_type(row_type: str, title: str) -> tuple[str, str]:
    """Return ``(value, reason)``. reason: preserved / via_keyword / via_override / miss."""
    if not is_empty(row_type):
        return str(row_type).strip(), "preserved"
    pick = pick_type_with_overrides(title)
    if pick["confidence"] == "high":
        reason_tag = "via_override" if pick["reason"] == "override" else "via_keyword"
        return pick["type"], reason_tag
    return "", "miss"


def fill_discipline(row_disc: str, title: str,
                    type_hint: str = "") -> tuple[str, str]:
    """Return ``(value, reason)``. reason: preserved / via_keyword / miss.

    ``value`` is the discipline_id as a decimal string when found, else "".
    """
    if not is_empty(row_disc):
        return str(row_disc).strip(), "preserved"
    pick = pick_discipline_with_overrides(title, type_hint=type_hint or None)
    if pick["confidence"] == "high" and pick["discipline_id"] is not None:
        return str(pick["discipline_id"]), "via_keyword"
    return "", "miss"


def classify_record(rec: Record) -> ClassificationResult:
    """The single per-row entry. Pure; no I/O. Composes the three helpers,
    feeding the just-inferred ``type`` as the discipline scorer's hint.
    """
    dt = normalize_doc_type(rec.doc_type, rec.title)
    ty = fill_type(rec.type, rec.title)
    di = fill_discipline(rec.discipline_id, rec.title, type_hint=ty[0])
    return ClassificationResult(
        FieldResult(*dt), FieldResult(*ty), FieldResult(*di),
    )
