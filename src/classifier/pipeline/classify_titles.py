"""Pure in-process title classifier (no I/O).

Public API: ``classify_titles(rows, include_reasons=False) -> list[dict]``

For consumers that already have rows in memory (a webhook payload, an
upload, a queue message) and don't want the classifier to touch a
database. Same per-row logic as ``classify_from_rds`` -- the RDS
pipeline is the same engine wrapped in a psycopg2 reader/writer.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from classifier.io.normalize import is_empty
from classifier.pipeline._row import (
    fill_discipline, fill_type, normalize_doc_type,
)


def classify_titles(rows: Iterable[Mapping],
                    *,
                    include_reasons: bool = False) -> list[dict]:
    """Classify a sequence of rows by title.

    Each input row must have a ``"title"`` key (string). Optional keys:

    * ``"doc_type"`` (text): preserved if non-empty/non-NULL.
    * ``"type"`` (text): preserved if non-empty/non-NULL.
    * ``"discipline_id"`` (int or string of int, or None): preserved if
      not empty/NULL.

    Any additional keys in the input row are ignored (not echoed back).
    If the caller needs to correlate inputs and outputs, they should
    keep their own ordered list -- the output is in the same order as
    the input.

    Returns a list of dicts, one per input row:

    .. code-block:: python

        {
            "doc_type":      "drawing" | "document",
            "type":          "DWG" | "ISO" | "" | ...,
            "discipline_id": int | None,
        }

    When ``include_reasons=True``, each value is a 2-tuple
    ``(value, reason_tag)`` where reason_tag is one of the documented
    classifier reason vocabularies (see ``pipeline/_row.py``).

    Behaviour mirrors ``classify_from_rds`` exactly:
      * ``doc_type`` is ALWAYS set (defaults to ``"document"`` on miss).
      * ``type`` and ``discipline_id`` are set only when confidence is
        ``"high"``; otherwise ``""`` / ``None``.
      * Existing populated fields are preserved verbatim.
    """
    out: list[dict] = []
    for row in rows:
        title = "" if row.get("title") is None else str(row["title"])

        cur_doc_type = row.get("doc_type")
        cur_type     = row.get("type")
        cur_disc     = row.get("discipline_id")

        cur_doc_type_s = "" if cur_doc_type is None else str(cur_doc_type)
        cur_type_s     = "" if cur_type     is None else str(cur_type)
        cur_disc_s     = "" if cur_disc     is None or is_empty(cur_disc) else str(cur_disc)

        new_doc_type, dt_reason = normalize_doc_type(cur_doc_type_s, title)
        new_type,     t_reason  = fill_type(cur_type_s, title)
        new_disc,     d_reason  = fill_discipline(cur_disc_s, title, type_hint=new_type)

        disc_value: int | None = int(new_disc) if new_disc else None

        if include_reasons:
            out.append({
                "doc_type":      (new_doc_type, dt_reason),
                "type":          (new_type, t_reason),
                "discipline_id": (disc_value, d_reason),
            })
        else:
            out.append({
                "doc_type":      new_doc_type,
                "type":          new_type,
                "discipline_id": disc_value,
            })
    return out
