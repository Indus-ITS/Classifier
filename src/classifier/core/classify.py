"""Core per-row classification: the single invariant entry point.

The three field helpers (``normalize_doc_type`` / ``fill_type`` /
``fill_discipline``) live here (relocated from ``pipeline/_row.py``, which now
re-exports them). ``classify_record`` composes them once so every execution
backend shares identical row logic.

Each helper takes ``(existing_value, title)`` and returns ``(value, reason)``.
"""
from __future__ import annotations

from classifier.config.buckets import TYPE_TO_BUCKET
from classifier.config.prose_guard import PROSE_DOC_PHRASES
from classifier.config.drawing_markers import DRAWING_TITLE_MARKERS, INDEX_MARKERS
from classifier.core.folding import doc_type_for_bucket
from classifier.core.discipline_scoring import pick_discipline_with_overrides
from classifier.core.type_scoring import pick_type_with_overrides, canonicalize_title, _phrase_matches
from classifier.core.record import Record, FieldResult, ClassificationResult
from classifier.io.normalize import is_empty

DRAWING_ALIASES = {"drawing", "drawings", "dwg"}
DOCUMENT_ALIASES = {"document", "documents", "doc", "docs"}
SHEET_ALIASES = {"sheet", "sheets"}


def _title_has(title: str, markers: tuple[tuple[str, ...], ...]) -> bool:
    """True iff the canonicalized title contains any marker phrase."""
    tokens = canonicalize_title(title)
    return any(_phrase_matches(tokens, list(m)) for m in markers)


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
    # Drawing words (DRAWING/SKETCH/LAYOUT) are structural nouns and win
    # over the prose guard — "HAZARDOUS AREA CLASSIFICATION LAYOUT" is a
    # layout drawing, not the prose schedule.
    if _title_has(title, DRAWING_TITLE_MARKERS):
        return "drawing", "drawing_title"
    if _title_has(title, PROSE_DOC_PHRASES):
        return "document", "prose_guard"
    if _title_has(title, INDEX_MARKERS):
        return "sheet", "index"
    pick = pick_type_with_overrides(title)
    bucket = TYPE_TO_BUCKET.get(pick["type"])
    if pick["confidence"] == "high" and bucket is not None:
        reason_tag = "via_override" if pick["reason"] == "override" else "via_keyword"
        return doc_type_for_bucket(bucket), reason_tag
    if bucket is not None and doc_type_for_bucket(bucket) == "sheet":
        return "sheet", "prefer_sheet"
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


def plan_writes(rec: Record, result: ClassificationResult) -> dict[str, object]:
    """Fields a sink should persist, applying only-fill-empty + doc_type diff.

    Returns {} when nothing should change (a "skipped" row). Faithful to the
    historical RDS write conditions: doc_type writes on a normalized diff;
    type/discipline write only when the existing value was empty AND inference
    produced a value. Values are returned in their core string form; a sink
    that needs another type (e.g. discipline_id as int for SQL) casts at write.
    """
    writes: dict[str, object] = {}
    if result.doc_type.value != rec.doc_type.strip().lower():
        writes["doc_type"] = result.doc_type.value
    if rec.type == "" and result.type.value != "":
        writes["type"] = result.type.value
    if rec.discipline_id == "" and result.discipline_id.value not in ("", None):
        writes["discipline_id"] = result.discipline_id.value
    return writes


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
