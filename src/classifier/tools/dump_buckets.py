"""Dump the description -> bucket -> class mapping as a CSV for human
review. Run from project root::

    dump-buckets

Writes output/bucket_mapping.csv with columns:
  - description: what the doc-type code means in the source data
  - mapped_bucket: which of the 10 buckets it gets labelled as
  - mapped_class: the 2-class fold (Drawings or Documents) for the bucket
  - status: 'ok' / 'ambiguous_skipped' (None mappings - skipped from ground truth)
  - code_count: how many distinct doc-type codes share this exact mapping
                (helpful for the 'Miscellaneous' descriptions which span
                multiple ambiguous numeric codes)

The internal 3-letter / numeric_2digit code-system distinction is omitted
- the senior reviewer cares about the description and the resulting
class, not the code that produced it. Rows are deduplicated on
(description, mapped_bucket, mapped_class, status); identical rows from
multiple codes collapse to one row with code_count > 1.

Sorted by mapped_class -> mapped_bucket -> description.
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pandas as pd

from classifier.config.buckets import BUCKET_TO_CLASS, TYPE_TO_BUCKET
from classifier.tools.harvest import NUMERIC_CODE_TO_BUCKET

OUT_PATH = Path("output/bucket_mapping.csv")

NUMERIC_DESC_SRC = Path(
    "input/classified/Sahil Drawings & Documents Index/"
    "16-99-11-1601_PROJECT DRAWING  INDEX _DWG_NATIVE & PDF_Sahil.xlsx"
)

TYPE_CODE_DESCRIPTION: dict = {
    "PID": "Piping & Instrumentation Diagram",
    "PFD": "Process Flow Diagram",
    "PSF": "Process Safety / Safeguarding Flow",
    "DGA": "General Arrangement Drawing",
    "DSD": "Standard Drawing",
    "DWG": "Drawing (general)",
    "DAL": "Alignment / Layout Drawing",
    "DWD": "Detail / Working Drawing",
    "DSL": "Single Line Diagram",
    "DBD": "Block Diagram",
    "DCE": "Cause & Effect Diagram",
    "DHZ": "Hazardous Area Drawing",
    "DPP": "Plot Plan Drawing",
    "MSD": "Mechanical Sketch / Mechanical Flow Diagram",
    "DAS": "Equipment Data Sheet",
    "SPC": "Specification",
    "STD": "Standard / Specification",
    "CAL": "Calculation",
    "REP": "Report",
    "BOD": "Basis of Design",
    "SOW": "Scope of Work",
    "LST": "List",
    "MTO": "Material Take-Off",
    "BOM": "Bill of Materials",
    "IDX": "Index",
    "REG": "Register",
    "SCH": "Schedule",
    "PRO": "Procedure",
    "PLN": "Plan",
    "PHL": "Philosophy",
    "REQ": "Requisition (e.g. Material Requisition)",
}


def load_numeric_descriptions() -> dict[int, str]:
    """Read the Document_Type sheet (paired CODE/DESCRIPTION columns)."""
    if not NUMERIC_DESC_SRC.exists():
        return {}
    df = pd.read_excel(NUMERIC_DESC_SRC, sheet_name="Document_Type", header=None)
    pairs: dict[int, str] = {}
    for col in range(0, df.shape[1], 2):
        if col + 1 >= df.shape[1]:
            break
        sub = df.iloc[:, [col, col + 1]].dropna(subset=[col])
        for _, row in sub.iterrows():
            code, desc = row.iloc[0], row.iloc[1]
            if isinstance(code, (int, float)) and pd.notna(desc):
                pairs[int(code)] = str(desc).strip()
    return pairs


def main() -> None:
    numeric_desc = load_numeric_descriptions()

    raw: list[tuple[str, str, str, str]] = []
    for code, bucket in NUMERIC_CODE_TO_BUCKET.items():
        raw.append((
            numeric_desc.get(code, ""),
            bucket if bucket else "",
            BUCKET_TO_CLASS.get(bucket, "") if bucket else "",
            "ok" if bucket else "ambiguous_skipped",
        ))
    for code, bucket in TYPE_TO_BUCKET.items():
        raw.append((
            TYPE_CODE_DESCRIPTION.get(code, ""),
            bucket,
            BUCKET_TO_CLASS.get(bucket, ""),
            "ok",
        ))

    counts = Counter(raw)
    rows: list[dict] = [
        {
            "description": desc,
            "mapped_bucket": bucket,
            "mapped_class": cls,
            "status": status,
            "code_count": n,
        }
        for (desc, bucket, cls, status), n in counts.items()
    ]

    class_order = {"Drawings": 0, "Documents": 1, "": 9}
    bucket_order = {
        "Drawings": 0, "Isometrics": 1, "Datasheets": 2, "Specifications": 3,
        "Calculations": 4, "Reports": 5, "Lists_MTOs_BOMs": 6,
        "Procedures_Plans": 7, "CRS": 8, "Documents": 9, "": 99,
    }
    rows.sort(key=lambda r: (
        class_order.get(r["mapped_class"], 50),
        bucket_order.get(r["mapped_bucket"], 50),
        r["description"].lower(),
    ))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cols = ("description", "mapped_bucket", "mapped_class", "status", "code_count")
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {OUT_PATH} - {len(rows)} unique mappings (from {sum(counts.values())} raw codes)")
    print()
    print("Counts by mapped class:")
    by_class: Counter = Counter()
    for (_, _, cls, status), n in counts.items():
        key = cls or f"(blank - {status})"
        by_class[key] += n
    for c, n in sorted(by_class.items(), key=lambda x: -x[1]):
        print(f"  {c:30s} {n:>3}")
    print()
    print("Counts by mapped bucket:")
    by_bucket: Counter = Counter()
    for (_, bucket, _, _), n in counts.items():
        by_bucket[bucket or "(ambiguous - skipped)"] += n
    for b, n in sorted(by_bucket.items(), key=lambda x: -x[1]):
        print(f"  {b:25s} {n:>3}")


if __name__ == "__main__":
    main()
