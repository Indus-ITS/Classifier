"""Pure in-process title classifier (no I/O).

Public API: ``classify_titles(rows, include_reasons=False) -> list[dict]``

For consumers that already have rows in memory (a webhook payload, an
upload, a queue message) and don't want the classifier to touch a
database. Same per-row logic as ``classify_from_rds`` -- the RDS
pipeline is the same engine wrapped in a psycopg2 reader/writer.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from classifier.io.memory import InMemoryReader, InMemoryWriter
from classifier.pipeline.run import run


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
    reader = InMemoryReader(rows)
    writer = InMemoryWriter()
    run(reader, writer)

    out: list[dict] = []
    for res in writer.results:
        disc_value = int(res.discipline_id.value) if res.discipline_id.value else None
        if include_reasons:
            out.append({
                "doc_type":      (res.doc_type.value, res.doc_type.reason),
                "type":          (res.type.value, res.type.reason),
                "discipline_id": (disc_value, res.discipline_id.reason),
            })
        else:
            out.append({
                "doc_type":      res.doc_type.value,
                "type":          res.type.value,
                "discipline_id": disc_value,
            })
    return out
