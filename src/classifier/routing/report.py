"""Sidecar report rows (pure) + CSV writer + console summary."""
from __future__ import annotations

import csv
from pathlib import Path

from classifier.routing.plan import Plan

REPORT_COLUMNS = (
    "customer_ref", "title", "class", "revision", "chosen_file",
    "chosen_format", "related_files", "related_count", "status",
)


def report_rows(plan: Plan, index) -> list[dict]:
    """One row per copy action plus rows for CSV entries that had no file.
    status: copied | unmatched-file | no-file-for-row.
    (skipped-no-preferred-format groups are summarized in the console, not
    the per-row sidecar, since they have no winner to name.)"""
    rows: list[dict] = []
    for a in plan.actions:
        status = "copied" if a.bucket != "Unmatched" else "unmatched-file"
        rows.append({
            "customer_ref": a.cust_ref or "",
            "title": a.title,
            "class": a.doc_type,
            "revision": a.revision or "",
            "chosen_file": a.dest.name,
            "chosen_format": a.chosen_format,
            "related_files": "; ".join(p.name for p in a.related),
            "related_count": str(len(a.related)),
            "status": status,
        })
    for ref in plan.rows_without_file:
        cls = index.get(ref)
        rows.append({
            "customer_ref": ref,
            "title": cls.title if cls else "",
            "class": (cls.doc_type if cls else ""),
            "revision": "", "chosen_file": "", "chosen_format": "",
            "related_files": "", "related_count": "0",
            "status": "no-file-for-row",
        })
    return rows


def write_report_csv(rows: list[dict], dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / "route-report.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REPORT_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return out


def print_summary(plan: Plan) -> None:
    copied = sum(1 for a in plan.actions if a.bucket != "Unmatched")
    unmatched = sum(1 for a in plan.actions if a.bucket == "Unmatched")
    dedup_dropped = sum(len(a.related) for a in plan.actions)
    print()
    print(f"groups with a winner:        {len(plan.actions)}")
    print(f"  copied to class buckets:   {copied}")
    print(f"  routed to Unmatched:       {unmatched}")
    print(f"siblings not copied:         {dedup_dropped}")
    print(f"rows with no file:           {len(plan.rows_without_file)}")
    print(f"skipped (no preferred fmt):  {len(plan.skipped_no_preferred_format)}")
