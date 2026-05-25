"""Shared per-row classifier logic.

Pure functions reused by:
  * ``classifier.cli.classify``        (CSV input/output)
  * ``classifier.pipeline.classify_rds`` (PostgreSQL input/output)

Each function takes ``(existing_value, title)`` and returns
``(new_value, reason_tag)`` so callers can build aggregate stats.
"""
from __future__ import annotations

from classifier.config.buckets import BUCKET_TO_CLASS, TYPE_TO_BUCKET
from classifier.core.type_scoring import pick_type_with_overrides
from classifier.io.normalize import is_empty

DRAWING_ALIASES = {"drawing", "drawings", "dwg"}
DOCUMENT_ALIASES = {"document", "documents", "doc", "docs"}


def normalize_doc_type(value: str, title: str) -> tuple[str, str]:
    """Return ``(normalized, reason)``. reason: existing / via_keyword / via_override / defaulted."""
    if not is_empty(value):
        v = str(value).strip().lower()
        if v in DRAWING_ALIASES:
            return "drawing", "existing"
        if v in DOCUMENT_ALIASES:
            return "document", "existing"
    pick = pick_type_with_overrides(title)
    if pick["confidence"] == "high":
        bucket = TYPE_TO_BUCKET.get(pick["type"])
        if bucket is not None:
            folded = BUCKET_TO_CLASS[bucket]
            reason_tag = "via_override" if pick["reason"] == "override" else "via_keyword"
            return ("drawing" if folded == "Drawings" else "document"), reason_tag
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


from classifier.core.discipline_scoring import pick_discipline_with_overrides


def fill_discipline(row_disc: str, title: str) -> tuple[str, str]:
    """Return ``(value, reason)``. reason: preserved / via_keyword / miss.

    ``value`` is the discipline_id as a decimal string when found, else
    ``""``. The RDS layer converts ``""`` to "omit from SET clause" and
    a non-empty string to ``int(...)`` before parameterising. The CSV
    CLI does not currently call this function.
    """
    if not is_empty(row_disc):
        return str(row_disc).strip(), "preserved"
    pick = pick_discipline_with_overrides(title)
    if pick["confidence"] == "high" and pick["discipline_id"] is not None:
        return str(pick["discipline_id"]), "via_keyword"
    return "", "miss"
