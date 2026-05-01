"""Main entry point: classify each row of the schedules under
``input/To be classified/`` and write a single CSV to ``output/classified.csv``.

Run from the project root::

    python classifier.py

Inputs:
  * ``input/To be classified/*.xls`` - schedule sheets with columns
    PCS Doc No., Cust Ref #, Title, Discip, Rev.
  * ``config.py`` - keyword bank, bucket definitions, BUCKET_TO_CLASS fold
  * ``helpers/classifier_lib.py`` - bucket scoring functions

Output:
  * ``output/classified.csv`` - one row per schedule entry, columns:
      title, doc_number, cust_ref, revision, discipline, class, subtype,
      source_sheet, discipline_inferred,
      score, top_weight, confidence, runner_up, runner_up_score
"""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from config import BUCKET_TO_CLASS
from helpers.classifier_lib import (
    discipline_from_keywords,
    fold_to_class,
    pick_bucket,
    score_buckets,
)

INPUT_DIR = Path("input/To be classified")
OUTPUT_PATH = Path("output/classified.csv")

# Column order: identity fields first, then primary classification (class),
# then secondary (subtype), then explainability fields. The first 7 are
# the user-facing columns; the rest are diagnostics for tuning.
COLUMNS = (
    "title",
    "doc_number",
    "cust_ref",
    "revision",
    "discipline",
    "class",
    "subtype",
    "source_sheet",
    "discipline_inferred",
    "score",
    "top_weight",
    "confidence",
    "runner_up",
    "runner_up_score",
)


def load_rows(xls_path: Path) -> list[dict]:
    df = pd.read_excel(xls_path, sheet_name="Sheet1")
    needed = {"PCS Doc No.", "Cust Ref #", "Title", "Discip", "Rev."}
    missing = needed - set(df.columns)
    if missing:
        raise SystemExit(f"{xls_path.name}: missing columns {missing}")

    df = df.dropna(subset=["Title"]).copy()
    rows = []
    for _, r in df.iterrows():
        title = str(r["Title"]).strip()
        if not title or title.lower() == "nan":
            continue
        scores = score_buckets(title, "")
        pick = pick_bucket(scores)
        subtype = pick["bucket"]
        rows.append({
            "title": title,
            "doc_number": "" if pd.isna(r["PCS Doc No."]) else str(r["PCS Doc No."]).strip(),
            "cust_ref": "" if pd.isna(r["Cust Ref #"]) else str(r["Cust Ref #"]).strip(),
            "revision": "" if pd.isna(r["Rev."]) else str(r["Rev."]).strip(),
            "discipline": "" if pd.isna(r["Discip"]) else str(r["Discip"]).strip(),
            "class": fold_to_class(pick, BUCKET_TO_CLASS),
            "subtype": subtype,
            "source_sheet": xls_path.name,
            "discipline_inferred": discipline_from_keywords(title),
            "score": pick["score_sum"],
            "top_weight": pick["score_top"],
            "confidence": pick["confidence"],
            "runner_up": pick["runner_up_bucket"],
            "runner_up_score": pick["runner_up_score"],
        })
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([r.get(c, "") for c in COLUMNS])


def main() -> None:
    if not INPUT_DIR.exists():
        raise SystemExit(f"input dir not found: {INPUT_DIR}")

    all_rows: list[dict] = []
    per_source: dict[str, int] = {}
    for xls in sorted(INPUT_DIR.glob("*.xls*")):
        rows = load_rows(xls)
        per_source[xls.name] = len(rows)
        all_rows.extend(rows)

    write_csv(all_rows, OUTPUT_PATH)

    print(f"\nWrote {OUTPUT_PATH}  ({len(all_rows)} rows)")
    print()
    print("By source sheet:")
    for name, n in per_source.items():
        print(f"  {name:30s} {n:>5}")
    print()
    from collections import Counter
    print("By class:")
    for cls, n in Counter(r["class"] for r in all_rows).most_common():
        print(f"  {cls:18s} {n:>5}  ({100*n/len(all_rows):5.1f}%)")
    print()
    print("By subtype:")
    for b, n in Counter(r["subtype"] for r in all_rows).most_common():
        print(f"  {b:18s} {n:>5}  ({100*n/len(all_rows):5.1f}%)")
    print()
    print("By discipline:")
    for d, n in Counter((r["discipline"] or "(blank)") for r in all_rows).most_common():
        print(f"  {d:18s} {n:>5}  ({100*n/len(all_rows):5.1f}%)")
    print()
    print("By class x discipline:")
    grid: dict[str, dict[str, int]] = {}
    for r in all_rows:
        cls = r["class"]
        disc = r["discipline"] or "(blank)"
        grid.setdefault(cls, {})
        grid[cls][disc] = grid[cls].get(disc, 0) + 1
    for cls in ("Drawings", "Documents", "Undefined"):
        if cls not in grid:
            continue
        total_cls = sum(grid[cls].values())
        print(f"  {cls} ({total_cls}):")
        for disc in sorted(grid[cls].keys()):
            print(f"    {disc:18s} {grid[cls][disc]:>5}")
    print()
    print("By confidence:")
    for conf, n in Counter(r["confidence"] for r in all_rows).most_common():
        print(f"  {conf:8s} {n:>5}  ({100*n/len(all_rows):5.1f}%)")


if __name__ == "__main__":
    main()
