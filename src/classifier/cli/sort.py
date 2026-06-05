"""sort-files: route deliverable files into class buckets using the
classified CSV as the source of truth. See
docs/superpowers/specs/2026-06-05-sort-files-router-design.md.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from classifier.io.classified_index import load_classified_index
from classifier.routing.dedup import group_files
from classifier.routing.plan import build_plan, BUCKET_FOR_DOCTYPE
from classifier.routing.execute import execute
from classifier.routing.report import report_rows, write_report_csv, print_summary

_SKIP_DIRS = set(BUCKET_FOR_DOCTYPE.values()) | {"Unmatched"}


def _iter_source_files(source_dir: Path):
    """All files under source_dir, recursive, skipping any already inside a
    bucket folder (so re-runs against the same tree are safe)."""
    for p in sorted(source_dir.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = set(p.relative_to(source_dir).parts[:-1])
        if rel_parts & _SKIP_DIRS:
            continue
        yield p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sort-files")
    ap.add_argument("--classified-csv", type=Path,
                    default=Path("output/classified.csv"))
    ap.add_argument("--source-dir", type=Path, required=True)
    ap.add_argument("--dest-dir", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not args.classified_csv.exists():
        raise SystemExit(f"classified CSV not found: {args.classified_csv}")
    if not args.source_dir.exists():
        raise SystemExit(f"source dir not found: {args.source_dir}")

    index = load_classified_index(args.classified_csv)
    files = list(_iter_source_files(args.source_dir))
    groups = group_files(files)
    plan = build_plan(groups, index, args.dest_dir)

    execute(plan, dry_run=args.dry_run)
    if not args.dry_run:
        out = write_report_csv(report_rows(plan, index), args.dest_dir)
        print(f"\nWrote {out}")
    else:
        print("\n[dry-run] no files copied, no report written")
    print_summary(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
