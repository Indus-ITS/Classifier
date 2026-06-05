"""Aggregate run statistics — a strict superset of every backend's legacy
stat vocabulary, so each edge can reconstruct its historical dict shape.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from classifier.core.record import Record, ClassificationResult
from classifier.io.normalize import is_empty


@dataclass
class Stats:
    rows_scanned: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0
    reasons: dict = field(default_factory=lambda: {
        "doc_type": Counter(), "type": Counter(), "discipline_id": Counter(),
    })
    doc_type_before: Counter = field(default_factory=Counter)
    doc_type_after: Counter = field(default_factory=Counter)
    callback_error: object = None

    def observe(self, rec: Record, result: ClassificationResult,
                writes: dict) -> None:
        self.rows_scanned += 1
        if writes:
            self.rows_updated += 1
        else:
            self.rows_skipped += 1
        self.reasons["doc_type"][result.doc_type.reason] += 1
        self.reasons["type"][result.type.reason] += 1
        self.reasons["discipline_id"][result.discipline_id.reason] += 1
        before = "" if is_empty(rec.doc_type) else rec.doc_type.strip().lower()
        self.doc_type_before[before or "(empty)"] += 1
        self.doc_type_after[result.doc_type.value] += 1
