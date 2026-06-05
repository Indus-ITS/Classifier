"""sort-by-source: copy one preferred file per logical document from labelled
source folders into doc_source buckets, splitting matched/unmatched via the
documents table. See docs/superpowers/specs/2026-06-05-sort-by-source-design.md.
"""
from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

import pandas as pd

from classifier.io.normalize import is_empty, normalize_lookup_key
from classifier.routing.source_plan import build_source_plan

REPORT_COLS = ("source", "customer_ref", "bucket", "matched",
               "chosen_file", "chosen_format", "related_count", "status")


def _load_doc_index(path: Path) -> dict[str, str]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[])
    for c in ("customer_ref", "doc_type"):
        if c not in df.columns:
            raise SystemExit(f"{path}: missing required column {c!r}")
    index: dict[str, str] = {}
    for _, row in df.iterrows():
        key = normalize_lookup_key(row["customer_ref"])
        if not key:
            continue
        index.setdefault(key, "" if is_empty(row["doc_type"])
                         else str(row["doc_type"]).strip().lower())
    return index


def _parse_source(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise SystemExit(f"--source must be LABEL=DIR, got {spec!r}")
    label, _, path = spec.partition("=")
    label = label.strip()
    if not label:
        raise SystemExit(f"--source missing label: {spec!r}")
    return label, Path(path.strip())


def _collect(d: Path) -> list[Path]:
    if not d.exists():
        raise SystemExit(f"source dir not found: {d}")
    return sorted(p for p in d.rglob("*") if p.is_file())


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
    ap.add_argument("--source", action="append", default=[], metavar="LABEL=DIR",
                    help="repeatable; e.g. feed=/path/to/feed")
    ap.add_argument("--documents", type=Path, required=True)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if not args.source:
        raise SystemExit("at least one --source LABEL=DIR is required")
    if not args.documents.exists():
        raise SystemExit(f"documents CSV not found: {args.documents}")

    doc_index = _load_doc_index(args.documents)
    sources = [(label, _collect(path)) for label, path in
               (_parse_source(s) for s in args.source)]
    plan = build_source_plan(sources, doc_index)

    taken: set[Path] = set()
    rows: list[dict] = []
    per_bucket: dict[str, int] = {}
    for a in plan.actions:
        dest = _unique_dest(args.dest / a.bucket / a.src.name, taken)
        taken.add(dest)
        if not args.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(a.src, dest)
        per_bucket[a.bucket] = per_bucket.get(a.bucket, 0) + 1
        rows.append({
            "source": a.bucket if a.matched else "(unmatched)",
            "customer_ref": a.customer_ref or "",
            "bucket": a.bucket,
            "matched": a.matched,
            "chosen_file": dest.name,
            "chosen_format": a.chosen_format,
            "related_count": len(a.related),
            "status": "copied",
        })

    if not args.dry_run:
        args.dest.mkdir(parents=True, exist_ok=True)
        report = args.dest / "route-by-source-report.csv"
        with report.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=REPORT_COLS, lineterminator="\n")
            w.writeheader()
            for r in rows:
                w.writerow(r)

    print(f"\n{'[dry-run] ' if args.dry_run else ''}planned {len(plan.actions)} copies "
          f"({len(plan.skipped_no_preferred)} groups skipped: no preferred format)")
    for b in sorted(per_bucket):
        print(f"  {b:14s} {per_bucket[b]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
