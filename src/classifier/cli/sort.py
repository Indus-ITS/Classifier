"""Interactive CLI to sort schedule-referenced files into class folders.

Reads a schedule.xls and a directory of files named by reference number.
For each logical document (group of files that share a stem after the
revision suffix is stripped), one winner is copied: latest revision in
the preferred format (pdf > doc/docx > xls/xlsx). Everything else
(older revisions, alternate formats, .dwg, .rar, attachments) is
recorded in <dest>/related-documents.xlsx.

Resulting layout under --dest-dir:

    Drawings/<discipline>/...
    Documents/<discipline>/...
    Undefined/<discipline>/...
    Unmatched/...
    related-documents.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from classifier.cli.colors import _Color, _color_enabled
from classifier.cli.prompts import _prompt, _prompt_path
from classifier.cli.reporting import (
    _print_match_summary,
    _print_plan_summary,
    _print_progress,
)
from classifier.io.related_xlsx import RelatedRow, write_related_xlsx
from classifier.routing.analysis import find_collisions
from classifier.routing.dedup import group_and_pick, parse_stem
from classifier.routing.execute import execute_plan
from classifier.routing.matching import _iter_source_files, match_files
from classifier.routing.plan import build_plan
from classifier.routing.resolution import resolve_duplicates
from classifier.routing.schedule_refs import load_schedule_refs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="sort-files",
        description="Copy schedule-referenced files into Drawings / Documents / "
                    "Undefined / Unmatched folders. One file per logical "
                    "document (latest revision; pdf > doc > xls).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  Interactive (prompts for dest-dir if omitted):
    sort-files --schedule schedule.xls --source-dir ./docs

  Non-interactive:
    sort-files --schedule schedule.xls --source-dir ./docs \\
        --dest-dir ./sorted --yes
""",
    )
    p.add_argument(
        "--schedule", required=True, type=Path,
        help="Path to the schedule .xls file (must have Sheet1 with a "
             "'Cust Ref #' and 'Title' column).",
    )
    p.add_argument(
        "--source-dir", required=True, type=Path,
        help="Directory containing the files to sort. Walked recursively. "
             "Files already inside class folders (Drawings/Documents/"
             "Undefined/Unmatched) are skipped so re-runs are safe.",
    )
    p.add_argument(
        "--dest-dir", type=Path, default=None,
        help="Destination directory. If omitted, you will be prompted.",
    )
    p.add_argument(
        "--include-title", action="store_true",
        help="Append the schedule's Title to the destination filename: "
             "'<original_stem> - <title><ext>'. Sanitized and truncated to "
             "--title-max-len chars. Unmatched files keep their original name.",
    )
    p.add_argument(
        "--title-max-len", type=int, default=100,
        help="Max characters of the title to include in the filename "
             "(default: 100). Only applies when --include-title is set.",
    )
    p.add_argument(
        "--on-duplicate", choices=("error", "skip", "rename"), default="error",
        help="What to do when two source files would land at the same "
             "destination. 'error' (default): abort. 'skip': keep first by "
             "path order. 'rename': append numeric suffix.",
    )
    p.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip the final confirmation prompt and execute immediately.",
    )
    p.add_argument(
        "--no-color", action="store_true",
        help="Disable ANSI color output (also disabled automatically when "
             "stdout is not a TTY or when NO_COLOR is set).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    c = _Color(_color_enabled(args.no_color))

    if not args.schedule.exists():
        print(c.red(f"error: schedule not found: {args.schedule}"), file=sys.stderr)
        return 2
    if not args.source_dir.is_dir():
        print(c.red(f"error: source-dir is not a directory: {args.source_dir}"), file=sys.stderr)
        return 2

    print(c.bold(f"Reading schedule: {args.schedule}"))
    try:
        refs = load_schedule_refs(args.schedule)
    except Exception as e:
        print(c.red(f"error reading schedule: {e}"), file=sys.stderr)
        return 2
    print(f"  {len(refs)} rows with valid cust_refs")

    print(c.bold(f"Scanning {args.source_dir} (recursive)"))
    all_files = _iter_source_files(args.source_dir)
    groups = group_and_pick(all_files)
    winners = [r.primary for r in groups.values()]
    related_by_winner = {r.primary: list(r.related) for r in groups.values()}
    accounted = set(winners) | {p for r in groups.values() for p in r.related}
    skipped_no_preferred = sum(1 for f in all_files if f not in accounted)
    print(f"  {len(all_files)} file(s) found, {len(winners)} winner(s) after dedup")
    if skipped_no_preferred:
        print(c.yellow(f"  {skipped_no_preferred} file(s) skipped (no preferred format in group)"))

    result = match_files(refs, args.source_dir, files=winners)
    _print_match_summary(result, c)

    if not result.matched and not result.unmatched:
        print(c.yellow("\nno files to sort - exiting."))
        return 0

    dest = args.dest_dir or _prompt_path("\nDestination directory")
    dest = Path(dest).expanduser().resolve()

    plan = build_plan(
        result,
        dest,
        include_title=args.include_title,
        title_max_len=args.title_max_len,
    )
    plan, dropped, renamed = resolve_duplicates(plan, args.on_duplicate)
    if dropped or renamed:
        print()
        if dropped:
            print(c.yellow(f"  --on-duplicate skip: {dropped} duplicate-name file(s) dropped"))
        if renamed:
            print(c.yellow(f"  --on-duplicate rename: {renamed} file(s) renamed with numeric suffix"))

    _print_plan_summary(plan, c)

    collisions = find_collisions(plan)
    if collisions:
        print()
        print(c.red(f"error: {len(collisions)} file(s) would overwrite existing destinations."))
        print(c.red("Use --on-duplicate skip to drop duplicates, or --on-duplicate rename to keep all."))
        for p in collisions[:10]:
            print(f"  {p}")
        if len(collisions) > 10:
            print(f"  ...and {len(collisions) - 10} more")
        print(c.red("\naborting."))
        return 1

    print()
    print(c.bold(f"Ready to copy {len(plan.operations)} file(s) into {dest}"))
    if not args.yes:
        if _prompt(f"Proceed?", valid=("yes", "no"), default="no") != "yes":
            print(c.yellow("cancelled."))
            return 0

    print()
    print(c.bold("Copying files..."))
    counts = execute_plan(
        plan,
        on_progress=lambda d, t, s: _print_progress(d, t, s, c),
    )

    rows = _build_related_rows(plan, result, related_by_winner, args.source_dir)
    xlsx_path = write_related_xlsx(dest, rows)

    print()
    print(c.green(c.bold("Done.")))
    print(f"  destination: {dest}")
    for name in ("Drawings", "Documents", "Undefined", "Unmatched"):
        n = counts.get(name, 0)
        if n:
            print(f"  {name:<12s} {n}")
    print(f"  related sidecar: {xlsx_path}")
    return 0


def _build_related_rows(plan, result, related_by_winner, source_root):
    matched_by_path = {m.path: m for m in result.matched}
    rows: list[RelatedRow] = []
    for src, dst in plan.operations:
        m = matched_by_path.get(src)
        _, revision = parse_stem(src.stem)
        ext = src.suffix.lstrip(".").lower()
        try:
            rel_dir = src.parent.relative_to(source_root).as_posix() or "."
        except ValueError:
            rel_dir = str(src.parent)
        rows.append(
            RelatedRow(
                cust_ref=m.cust_ref if m else "",
                title=m.title if m else "",
                class_label=m.class_label if m else "",
                discipline=m.discipline if m else "",
                revision=revision,
                chosen_file=dst.name,
                chosen_format=ext,
                related_files=[p.name for p in related_by_winner.get(src, [])],
                source_group_dir=rel_dir,
            )
        )
    return rows


if __name__ == "__main__":
    sys.exit(main())
