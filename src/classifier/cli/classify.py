"""Fill ``doc_type`` and ``type`` in the to-be-classified CSV.

Reads ``input/To be classified/document.csv`` and writes
``output/classified.csv`` with identical schema, identical column order,
identical row count. Only ``doc_type`` and ``type`` may change.

* ``doc_type`` is always normalized to the lowercase enum
  ``{drawing, document}``. Unknown/empty values fall back to the
  bucket scorer; ``Undefined`` folds to ``document`` (intentional
  business bias - see the spec).
* ``type`` is filled only when the input value is empty/NULL, by
  looking up the row's ``document_no`` (then ``customer_ref``) in the
  maps built from ``input/classified_csv/``. On miss it stays empty.

Run from project root::

    classify
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pandas as pd

from classifier.config.buckets import BUCKET_TO_CLASS, TYPE_TO_BUCKET
from classifier.core.scoring import fold_to_class, pick_bucket, score_buckets
from classifier.core.type_scoring import pick_type, score_types
from classifier.io.normalize import is_empty, normalize_lookup_key
from classifier.io.schema import TARGET_COLUMNS, validate_schema
from classifier.io.type_lookup import TypeLookup, build_lookup

INPUT_PATH = Path("input/To be classified/document.csv")
OUTPUT_PATH = Path("output/classified.csv")
CLASSIFIED_CSV_DIR = Path("input/classified_csv")
TYPE_KEYWORDS_PATH = Path("src/classifier/config/type_keywords.py")

DRAWING_ALIASES = {"drawing", "drawings", "dwg"}
DOCUMENT_ALIASES = {"document", "documents", "doc", "docs"}


def _normalize_doc_type(value: str, title: str, description: str) -> tuple[str, str]:
    """Return ``(normalized, reason)``.

    reason is one of: ``existing``, ``via_keyword``, ``scored``.

    Path:
      1. Existing value normalizes to drawing/document via the aliases.
      2. Else: pick_type(title); if confidence=='high', fold via
         TYPE_TO_BUCKET + BUCKET_TO_CLASS to drawing/document.
      3. Else: bucket-level score_buckets fallback; Undefined -> document.
    """
    if not is_empty(value):
        v = str(value).strip().lower()
        if v in DRAWING_ALIASES:
            return "drawing", "existing"
        if v in DOCUMENT_ALIASES:
            return "document", "existing"
    pick = pick_type(score_types(title))
    if pick["confidence"] == "high":
        bucket = TYPE_TO_BUCKET.get(pick["type"])
        if bucket is not None:
            folded = BUCKET_TO_CLASS[bucket]
            return ("drawing" if folded == "Drawings" else "document"), "via_keyword"
    scores = score_buckets(title, description)
    bucket_pick = pick_bucket(scores)
    folded = fold_to_class(bucket_pick, BUCKET_TO_CLASS)
    return ("drawing" if folded == "Drawings" else "document"), "scored"


def _fill_type(row_type: str, doc_no: str, cust_ref: str,
               title: str, lookup: TypeLookup) -> tuple[str, str]:
    """Return ``(value, reason)``.

    reason is one of: ``preserved``, ``via_doc_no``, ``via_cross_ref``,
    ``via_cust_ref``, ``via_keyword``, ``empty``.

    Tiers (first non-empty wins):
      1. existing value (preserved).
      2. ``input.document_no`` against ``lookup.by_doc_no``.
         Reason: ``via_doc_no``.
      3. ``input.customer_ref`` against ``lookup.by_doc_no`` - the
         input's ``customer_ref`` typically carries the original
         document number that appears as ``document_no`` in the
         canonical index. This is the dominant healthy fill path on
         the current dataset, because the input system uses a different
         identifier scheme for the same record.
         Reason: ``via_cross_ref``.
      4. ``input.customer_ref`` against ``lookup.by_cust_ref`` - only
         fires when a canonical CSV ever populates its own
         ``customer_ref`` column (currently always empty on this
         dataset).
         Reason: ``via_cust_ref``.
      5. ``pick_type(title)`` with confidence == 'high'.
         Reason: ``via_keyword``.
      6. Miss -> empty.
    """
    if not is_empty(row_type):
        return str(row_type).strip(), "preserved"
    k_doc = normalize_lookup_key(doc_no)
    if k_doc and k_doc in lookup.by_doc_no:
        return lookup.by_doc_no[k_doc], "via_doc_no"
    k_cust = normalize_lookup_key(cust_ref)
    if k_cust:
        if k_cust in lookup.by_doc_no:
            return lookup.by_doc_no[k_cust], "via_cross_ref"
        if k_cust in lookup.by_cust_ref:
            return lookup.by_cust_ref[k_cust], "via_cust_ref"
    pick = pick_type(score_types(title))
    if pick["confidence"] == "high":
        return pick["type"], "via_keyword"
    return "", "empty"


def main() -> None:
    if not INPUT_PATH.exists():
        raise SystemExit(f"input not found: {INPUT_PATH}")

    df = pd.read_csv(INPUT_PATH, dtype=str, keep_default_na=False, na_values=[])
    validate_schema(df.columns)

    # Warn if type_keywords.py is older than any training CSV. Non-blocking.
    if TYPE_KEYWORDS_PATH.exists():
        rules_mtime = TYPE_KEYWORDS_PATH.stat().st_mtime
        csv_mtimes = [
            p.stat().st_mtime for p in CLASSIFIED_CSV_DIR.rglob("*.csv")
        ]
        if csv_mtimes and max(csv_mtimes) > rules_mtime:
            print("!! WARNING: type_keywords.py is older than training data. "
                  "Run: learn-type-keywords")

    lookup = build_lookup(CLASSIFIED_CSV_DIR)

    doc_type_before: Counter[str] = Counter()
    doc_type_after: Counter[str] = Counter()
    doc_type_reason: Counter[str] = Counter()
    type_reason: Counter[str] = Counter()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writerow(TARGET_COLUMNS)
        for _, row in df.iterrows():
            # Preserve original byte values for non-target columns. Only
            # doc_type and type are mutated; everything else is passed
            # through verbatim (including sentinels like "NULL").
            out = {c: str(row[c]) for c in TARGET_COLUMNS}

            before = out["doc_type"].strip().lower() if not is_empty(out["doc_type"]) else ""
            doc_type_before[before or "(empty)"] += 1

            new_doc_type, dt_reason = _normalize_doc_type(
                out["doc_type"], out["title"], out["description"],
            )
            out["doc_type"] = new_doc_type
            doc_type_after[new_doc_type] += 1
            doc_type_reason[dt_reason] += 1

            new_type, t_reason = _fill_type(
                out["type"], out["document_no"], out["customer_ref"],
                out["title"], lookup,
            )
            out["type"] = new_type
            type_reason[t_reason] += 1

            writer.writerow([out[c] for c in TARGET_COLUMNS])

    total = sum(doc_type_after.values())
    fills = (type_reason["via_doc_no"]
             + type_reason["via_cross_ref"]
             + type_reason["via_cust_ref"]
             + type_reason["via_keyword"])

    print(f"\nWrote {OUTPUT_PATH}  ({total} rows)")
    print()
    print(f"Lookup: scanned {lookup.n_csvs} csvs; "
          f"doc_no map={len(lookup.by_doc_no)}, "
          f"cust_ref map={len(lookup.by_cust_ref)}, "
          f"conflicts doc_no={len(lookup.conflicts_doc_no)} "
          f"cust_ref={len(lookup.conflicts_cust_ref)}")
    print()
    print("doc_type (before -> after):")
    for k in sorted(set(doc_type_before) | set(doc_type_after)):
        print(f"  {k:14s} before={doc_type_before.get(k, 0):>6}  "
              f"after={doc_type_after.get(k, 0):>6}")
    print(f"  reasons: {dict(doc_type_reason)}")
    print()
    print("type fill outcomes:")
    for k in ("preserved", "via_doc_no", "via_cross_ref",
              "via_cust_ref", "via_keyword", "empty"):
        print(f"  {k:14s} {type_reason.get(k, 0):>6}")

    if fills > 0 and type_reason["via_cust_ref"] / fills > 0.10:
        ratio = type_reason["via_cust_ref"] / fills
        print()
        print(f"!! WARNING: true cust_ref fallback is {ratio:.1%} of fills (>10%).")
        print("   Customer refs are reused/human-entered — verify upstream data.")

    if lookup.conflicts_doc_no:
        print()
        print(f"!! conflict keys in doc_no map ({len(lookup.conflicts_doc_no)}):")
        for k, ts in list(lookup.conflicts_doc_no.items())[:10]:
            print(f"   {k} -> {sorted(ts)}")
        if len(lookup.conflicts_doc_no) > 10:
            print(f"   ... +{len(lookup.conflicts_doc_no) - 10} more")


if __name__ == "__main__":
    main()
