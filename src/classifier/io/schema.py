"""Canonical 28-column CSV schema shared by every CSV producer/consumer.

Source of truth: ``input/To be classified/document.csv`` header row.
All pipeline stages must read and write rows in this exact order.
"""
from __future__ import annotations

from collections import Counter
from typing import Sequence

TARGET_COLUMNS: tuple[str, ...] = (
    "document_id",
    "entity_id",
    "document_no",
    "doc_type",
    "status",
    "description",
    "date_modified",
    "modified_by",
    "category",
    "discipline_id",
    "title",
    "rev",
    "reference_link",
    "volume",
    "book",
    "customer_ref",
    "doc_source",
    "parent_discipline_id",
    "type",
    "entity_source",
    "hash",
    "metadata",
    "extracted_at",
    "extractor_version",
    "last_updated_at",
    "updated_by",
    "rfp_id",
    "toc_json",
)


def validate_schema(columns: Sequence[str]) -> None:
    """Hard-fail unless ``columns`` matches TARGET_COLUMNS exactly.

    Checks length, order, and absence of duplicates. Raises SystemExit
    with a diff-style message on mismatch so the call-site stops the
    pipeline immediately instead of writing corrupt CSV downstream.
    """
    got = tuple(columns)
    if got == TARGET_COLUMNS:
        return

    expected = list(TARGET_COLUMNS)
    actual = list(got)
    missing = [c for c in expected if c not in actual]
    extra = [c for c in actual if c not in expected]
    out_of_order = (
        sorted(expected) == sorted(actual) and expected != actual
    )
    duplicates = [c for c, n in Counter(actual).items() if n > 1]
    msg = ["schema mismatch:"]
    if len(actual) != len(expected):
        msg.append(f"  length: got {len(actual)}, expected {len(expected)}")
    if missing:
        msg.append(f"  missing: {missing}")
    if extra:
        msg.append(f"  extra: {extra}")
    if out_of_order:
        msg.append("  order differs from TARGET_COLUMNS")
    if duplicates:
        msg.append(f"  duplicates: {duplicates}")
    raise SystemExit("\n".join(msg))
