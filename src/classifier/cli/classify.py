"""Fill ``doc_type`` and ``type`` in the to-be-classified CSV.

Title-only classifier. Reads ``input/To be classified/document.csv``,
fills ``doc_type`` and ``type`` from the row's ``title`` alone, writes
``output/classified.csv`` with identical schema, identical column order,
identical row count. Only ``doc_type`` and ``type`` may differ.

* ``doc_type`` is normalized to the lowercase enum ``{drawing, document}``.
  Existing values fold via DRAWING_ALIASES / DOCUMENT_ALIASES. Empty /
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

import csv
from collections import Counter
from pathlib import Path

import pandas as pd

from classifier.io.normalize import is_empty
from classifier.io.schema import TARGET_COLUMNS, validate_schema
from classifier.pipeline._row import fill_type, normalize_doc_type

INPUT_PATH = Path("input/To be classified/document.csv")
OUTPUT_PATH = Path("output/classified.csv")
CLASSIFIED_CSV_DIR = Path("input/classified_csv")
TYPE_KEYWORDS_PATH = Path("src/classifier/config/type_keywords.py")


def main() -> None:
    if not INPUT_PATH.exists():
        raise SystemExit(f"input not found: {INPUT_PATH}")

    df = pd.read_csv(INPUT_PATH, dtype=str, keep_default_na=False, na_values=[])
    validate_schema(df.columns)

    # Stale-rules warning: type_keywords.py vs newest training CSV.
    if TYPE_KEYWORDS_PATH.exists() and CLASSIFIED_CSV_DIR.exists():
        rules_mtime = TYPE_KEYWORDS_PATH.stat().st_mtime
        csv_mtimes = [p.stat().st_mtime for p in CLASSIFIED_CSV_DIR.rglob("*.csv")]
        if csv_mtimes and max(csv_mtimes) > rules_mtime:
            print("!! WARNING: type_keywords.py is older than training data. "
                  "Run: learn-type-keywords")

    doc_type_before: Counter[str] = Counter()
    doc_type_after: Counter[str] = Counter()
    doc_type_reason: Counter[str] = Counter()
    type_reason: Counter[str] = Counter()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writerow(TARGET_COLUMNS)
        for _, row in df.iterrows():
            # Preserve original byte values for non-target columns.
            out = {c: str(row[c]) for c in TARGET_COLUMNS}

            before = out["doc_type"].strip().lower() if not is_empty(out["doc_type"]) else ""
            doc_type_before[before or "(empty)"] += 1

            new_doc_type, dt_reason = normalize_doc_type(out["doc_type"], out["title"])
            out["doc_type"] = new_doc_type
            doc_type_after[new_doc_type] += 1
            doc_type_reason[dt_reason] += 1

            new_type, t_reason = fill_type(out["type"], out["title"])
            out["type"] = new_type
            type_reason[t_reason] += 1

            writer.writerow([out[c] for c in TARGET_COLUMNS])

    total = sum(doc_type_after.values())
    print(f"\nWrote {OUTPUT_PATH}  ({total} rows)")
    print()
    print("doc_type (before -> after):")
    for k in sorted(set(doc_type_before) | set(doc_type_after)):
        print(f"  {k:20s} before={doc_type_before.get(k, 0):>6}  "
              f"after={doc_type_after.get(k, 0):>6}")
    print(f"  reasons: {dict(doc_type_reason)}")
    print()
    print("type fill outcomes:")
    for k in ("preserved", "via_override", "via_keyword", "miss"):
        print(f"  {k:14s} {type_reason.get(k, 0):>6}")


if __name__ == "__main__":
    main()
