"""Filter output/classified.csv down to just the rows where class='Undefined'
and write them to output/undefined_for_review.csv with only the columns useful
for human review (drops score/runner_up/confidence which are constant for
zero-score fallthroughs).

Run from project root::

    python helpers/dump_undefined.py
"""
from __future__ import annotations

import csv
from pathlib import Path

INPUT = Path("output/classified.csv")
OUTPUT = Path("output/undefined_for_review.csv")

REVIEW_COLUMNS = (
    "title",
    "doc_number",
    "cust_ref",
    "revision",
    "discipline",
    "source_sheet",
)


def main() -> None:
    if not INPUT.exists():
        raise SystemExit(f"input not found: {INPUT}. Run 'python classifier.py' first.")

    rows = []
    with INPUT.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["class"] == "Undefined":
                rows.append({c: r.get(c, "") for c in REVIEW_COLUMNS})

    # Stable order: by source sheet, then discipline, then title - so
    # reviewers can scan related items together.
    rows.sort(key=lambda r: (r["source_sheet"], r["discipline"], r["title"]))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {OUTPUT}  ({len(rows)} undefined rows)")
    print()
    from collections import Counter
    print("By source sheet:")
    for s, n in Counter(r["source_sheet"] for r in rows).most_common():
        print(f"  {s:30s} {n:>4}")
    print()
    print("By discipline:")
    for d, n in Counter(r["discipline"] for r in rows).most_common():
        print(f"  {d or '(blank)':18s} {n:>4}")


if __name__ == "__main__":
    main()
