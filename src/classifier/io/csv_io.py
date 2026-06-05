"""CSV RecordReader/ResultWriter for the standalone `classify` CLI.

CsvReader streams the 28-column input, validating the schema, and carries each
full original row as the Record.handle so non-target columns pass through
untouched. CsvWriter rewrites every row (full-row sink) applying the three
classified fields from the result; it ignores `writes` because the CSV output
always re-emits all columns.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator

import pandas as pd

from classifier.core.record import Record, ClassificationResult
from classifier.io.schema import TARGET_COLUMNS, validate_schema


class CsvReader:
    def __init__(self, path: Path):
        self.path = path

    def __iter__(self) -> Iterator[Record]:
        df = pd.read_csv(self.path, dtype=str, keep_default_na=False, na_values=[])
        validate_schema(df.columns)
        for _, row in df.iterrows():
            original = {c: str(row[c]) for c in TARGET_COLUMNS}
            yield Record(
                title=original["title"],
                doc_type=original["doc_type"],
                type=original["type"],
                discipline_id=original["discipline_id"],
                handle=original,
            )

    def close(self) -> None:
        pass


class CsvWriter:
    def __init__(self, path: Path):
        self.path = path
        self._f = None
        self._w = None

    def _ensure_open(self):
        if self._w is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._f = self.path.open("w", newline="", encoding="utf-8")
            self._w = csv.writer(self._f, quoting=csv.QUOTE_MINIMAL,
                                 lineterminator="\n")
            self._w.writerow(TARGET_COLUMNS)

    def write(self, rec: Record, result: ClassificationResult, writes) -> None:
        self._ensure_open()
        out = dict(rec.handle)   # full original row
        out["doc_type"] = result.doc_type.value
        out["type"] = result.type.value
        out["discipline_id"] = result.discipline_id.value
        self._w.writerow([out[c] for c in TARGET_COLUMNS])

    def close(self) -> None:
        if self._f is not None:
            self._f.close()
