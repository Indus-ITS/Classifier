"""Pure data types shared across the classifier core and all backends.

No I/O, no behavior — just the record-in / result-out shapes that the core
entry point (``classify_record``) consumes and produces.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Record:
    """One row to classify. Raw existing values are strings; "" means empty.

    ``handle`` is an opaque value a writer may need to persist the result
    (a PK, a full source row, a list index). The core never inspects it.
    """
    title: str
    doc_type: str = ""
    type: str = ""
    discipline_id: str = ""
    handle: object = None


@dataclass(frozen=True)
class FieldResult:
    value: object
    reason: str


@dataclass(frozen=True)
class ClassificationResult:
    doc_type: FieldResult
    type: FieldResult
    discipline_id: FieldResult
