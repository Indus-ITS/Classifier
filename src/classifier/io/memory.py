"""In-memory RecordReader/ResultWriter for callers holding rows already.

The writer collects ClassificationResults in input order; classify_titles
renders the public dict shape from them.
"""
from __future__ import annotations

from typing import Iterable, Iterator, Mapping

from classifier.core.record import Record, ClassificationResult
from classifier.io.normalize import is_empty


class InMemoryReader:
    def __init__(self, rows: Iterable[Mapping]):
        self._rows = rows

    def __iter__(self) -> Iterator[Record]:
        for row in self._rows:
            title = "" if row.get("title") is None else str(row["title"])
            dt = row.get("doc_type")
            ty = row.get("type")
            di = row.get("discipline_id")
            yield Record(
                title=title,
                doc_type="" if dt is None else str(dt),
                type="" if ty is None else str(ty),
                discipline_id="" if di is None or is_empty(di) else str(di),
            )

    def close(self) -> None:
        pass


class InMemoryWriter:
    def __init__(self):
        self.results: list[ClassificationResult] = []

    def write(self, rec: Record, result: ClassificationResult, writes) -> None:
        self.results.append(result)

    def close(self) -> None:
        pass
