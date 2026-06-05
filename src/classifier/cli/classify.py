"""Fill ``doc_type`` and ``type`` in the to-be-classified CSV.

Title-only classifier. Reads ``input/To be classified/document.csv``,
fills ``doc_type`` and ``type`` from the row's ``title`` alone, writes
``output/classified.csv`` with identical schema, identical column order,
identical row count. Only ``doc_type`` and ``type`` may differ.

* ``doc_type`` is normalized to the lowercase enum ``{drawing, document, sheet}``.
  Existing values fold via DRAWING_ALIASES / SHEET_ALIASES /
  DOCUMENT_ALIASES. Empty /
  unrecognized values fall back to ``pick_type(score_types(title))``;
  when confidence is ``high``, derive doc_type from the picked type's
  bucket. Otherwise default to ``document`` (intentional business bias).
* ``type`` preserves any existing non-empty value; otherwise fills from
  ``pick_type(score_types(title))`` when confidence is ``high``; otherwise
  empty.

Stale-rules warning: prints when ``type_keywords.py`` is older than any
training CSV under ``input/classified_csv/``.

Run from project root::

    classify
"""
from __future__ import annotations

from pathlib import Path

from classifier.io.csv_io import CsvReader, CsvWriter
from classifier.pipeline.run import run

INPUT_PATH = Path("input/To be classified/document.csv")
OUTPUT_PATH = Path("output/classified.csv")


def main() -> None:
    if not INPUT_PATH.exists():
        raise SystemExit(f"input not found: {INPUT_PATH}")

    reader = CsvReader(INPUT_PATH)
    writer = CsvWriter(OUTPUT_PATH)
    stats = run(reader, writer)

    total = sum(stats.doc_type_after.values())
    print(f"\nWrote {OUTPUT_PATH}  ({total} rows)")
    print()
    print("doc_type (before -> after):")
    for k in sorted(set(stats.doc_type_before) | set(stats.doc_type_after)):
        print(f"  {k:20s} before={stats.doc_type_before.get(k, 0):>6}  "
              f"after={stats.doc_type_after.get(k, 0):>6}")
    print(f"  reasons: {dict(stats.reasons['doc_type'])}")
    print()
    print("type fill outcomes:")
    for k in ("preserved", "via_override", "via_keyword", "miss"):
        print(f"  {k:14s} {stats.reasons['type'].get(k, 0):>6}")
    print()
    print("discipline_id fill outcomes:")
    for k in ("preserved", "via_keyword", "miss"):
        print(f"  {k:14s} {stats.reasons['discipline_id'].get(k, 0):>6}")


if __name__ == "__main__":
    main()
