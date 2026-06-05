"""sort-by-source: CSV-driven file router.

For each row of a documents-table export, find its file across the given source
folders and copy ONE preferred-format file into a bucket named by the row's
``doc_source`` (so matched buckets never exceed their CSV row count). Leftover
files bearing a cust_ref the table doesn't list go to ``unmatched``. See
docs/superpowers/specs/2026-06-05-sort-by-source-design.md.
"""
from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

import pandas as pd

from classifier.io.normalize import is_empty
from classifier.routing.source_plan import DocRow, build_plan

REPORT_COLS = ("bucket", "key", "matched", "doc_source",
               "chosen_file", "chosen_format", "related_count")


def _load_rows(path: Path) -> list[DocRow]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[])
    for c in ("customer_ref", "document_no", "doc_source", "doc_type"):
        if c not in df.columns:
            raise SystemExit(f"{path}: missing required column {c!r}")
    rows: list[DocRow] = []
    for _, r in df.iterrows():
        rows.append(DocRow(
            customer_ref="" if is_empty(r["customer_ref"]) else str(r["customer_ref"]),
            document_no="" if is_empty(r["document_no"]) else str(r["document_no"]),
            doc_source="" if is_empty(r["doc_source"]) else str(r["doc_source"]).strip().lower(),
            doc_type="" if is_empty(r["doc_type"]) else str(r["doc_type"]).strip().lower(),
        ))
    return rows


def _collect(dirs: list[Path]) -> list[Path]:
    files: list[Path] = []
    for d in dirs:
        if not d.exists():
            raise SystemExit(f"source dir not found: {d}")
        files.extend(p for p in d.rglob("*") if p.is_file())
    return sorted(files)


def _unique_dest(dest: Path, taken: set[Path]) -> Path:
    if dest not in taken:
        return dest
    n = 2
    while True:
        cand = dest.with_name(f"{dest.stem}-{n}{dest.suffix}")
        if cand not in taken:
            return cand
        n += 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sort-by-source")
    ap.add_argument("--documents", type=Path, required=True,
                    help="documents-table export CSV (the master list)")
    ap.add_argument("--source", action="append", default=[], type=Path,
                    metavar="DIR", help="repeatable; a folder to scan for files")
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if not args.source:
        raise SystemExit("at least one --source DIR is required")
    if not args.documents.exists():
        raise SystemExit(f"documents CSV not found: {args.documents}")

    rows = _load_rows(args.documents)
    files = _collect(args.source)
    plan = build_plan(rows, files)

    taken: set[Path] = set()
    per_bucket: dict[str, int] = {}
    report: list[dict] = []
    for a in plan.actions:
        dest = _unique_dest(args.dest / a.bucket / a.src.name, taken)
        taken.add(dest)
        if not args.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(a.src, dest)
        per_bucket[a.bucket] = per_bucket.get(a.bucket, 0) + 1
        report.append({
            "bucket": a.bucket, "key": a.key, "matched": a.matched,
            "doc_source": a.doc_source, "chosen_file": dest.name,
            "chosen_format": a.chosen_format, "related_count": len(a.related),
        })

    if not args.dry_run:
        args.dest.mkdir(parents=True, exist_ok=True)
        rpt = args.dest / "route-by-source-report.csv"
        with rpt.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=REPORT_COLS, lineterminator="\n")
            w.writeheader()
            for r in report:
                w.writerow(r)

    tag = "[dry-run] " if args.dry_run else ""
    print(f"\n{tag}{len(rows)} CSV rows | {len(files)} files scanned | "
          f"{len(plan.actions)} copies")
    for b in sorted(per_bucket):
        print(f"  {b:14s} {per_bucket[b]}")
    print(f"  rows with no file:           {len(plan.rows_without_file)}")
    print(f"  skipped (no preferred fmt):  {len(plan.skipped_no_preferred)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
