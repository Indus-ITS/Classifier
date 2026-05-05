"""Interactive CLI to sort schedule-referenced files into class folders.

Reads a schedule.xls and a directory of files named by reference number,
matches them, then either sorts in-place or copies into a destination
folder layout:

    Drawings/      - matched, class==Drawings
    Documents/     - matched, class==Documents
    Undefined/     - matched, class==Undefined (no keyword fired)
    Unmatched/     - cust_ref not found in schedule (or no ref in filename)

This module is the user interface (argparse, prompts, color, progress).
All routing logic lives in classifier.routing.

Usage examples:

    sort-files --schedule input/sahil_schedule.xls --source-dir /tmp/docs

    sort-files --schedule input/sahil_schedule.xls --source-dir /tmp/docs \\
        --mode copy --dest-dir /tmp/sorted --yes

    sort-files --schedule input/sahil_schedule.xls --source-dir /tmp/docs \\
        --mode in-place --yes

Run with --help for full options.
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
from classifier.routing.analysis import find_collisions
from classifier.routing.execute import clean_empty_dirs, execute_plan
from classifier.routing.matching import match_files
from classifier.routing.plan import build_plan
from classifier.routing.resolution import resolve_duplicates
from classifier.routing.schedule_refs import load_schedule_refs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="sort-files",
        description="Sort schedule-referenced files into Drawings / Documents / "
                    "Undefined / Unmatched folders. Files are matched to "
                    "schedule rows by their cust_ref number embedded in the filename.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  Interactive:
    sort-files --schedule schedule.xls --source-dir ./docs

  Copy mode, non-interactive:
    sort-files --schedule schedule.xls --source-dir ./docs \\
        --mode copy --dest-dir ./sorted --yes

  In-place sort, non-interactive:
    sort-files --schedule schedule.xls --source-dir ./docs \\
        --mode in-place --yes
""",
    )
    p.add_argument(
        "--schedule", required=True, type=Path,
        help="Path to the schedule .xls file (must have Sheet1 with a "
             "'Cust Ref #' and 'Title' column).",
    )
    p.add_argument(
        "--source-dir", required=True, type=Path,
        help="Directory containing the files to sort. Top level only by "
             "default (subdirectories are skipped). Pass --recursive to "
             "walk subdirectories.",
    )
    p.add_argument(
        "--recursive", "-r", action="store_true",
        help="Recursively scan subdirectories of --source-dir. Files "
             "already inside class folders (Drawings/Documents/Undefined/"
             "Unmatched) are skipped so re-runs are safe. After in-place "
             "sort, the original subdirs may be left empty - pair with "
             "--clean-empty-dirs to remove them.",
    )
    p.add_argument(
        "--clean-empty-dirs", action="store_true",
        help="After execution, remove any subdirectories under --source-dir "
             "(or --dest-dir for copy) that are now empty. Useful with "
             "--recursive + --mode in-place to clean up emptied "
             "transmittal folders.",
    )
    p.add_argument(
        "--include-title", action="store_true",
        help="Append the schedule's Title to the destination filename: "
             "'<original_stem> - <title><ext>'. The title is sanitized for "
             "filesystem safety and truncated to --title-max-len chars. "
             "Files with no schedule match (Unmatched) keep their original name.",
    )
    p.add_argument(
        "--title-max-len", type=int, default=100,
        help="Max characters of the title to include in the filename "
             "(default: 100). Only applies when --include-title is set.",
    )
    p.add_argument(
        "--on-duplicate", choices=("error", "skip", "rename"), default="error",
        help="What to do when two source files would land at the same "
             "destination (common with --recursive when the same document "
             "was re-sent across transmittals). "
             "'error' (default): abort with a list of collisions. "
             "'skip': keep the first source by path order, drop the rest. "
             "'rename': keep all by appending a numeric suffix "
             "(foo.pdf, foo-2.pdf, foo-3.pdf, ...). "
             "Also handles cases where the destination already exists on disk.",
    )
    p.add_argument(
        "--mode", choices=("in-place", "copy"), default=None,
        help="'in-place' moves files into class subfolders of --source-dir. "
             "'copy' copies into --dest-dir. If omitted, you will be prompted.",
    )
    p.add_argument(
        "--dest-dir", type=Path, default=None,
        help="Destination directory for --mode copy. If omitted, you will "
             "be prompted (only when --mode copy).",
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

    # ---- Validate paths --------------------------------------------------
    if not args.schedule.exists():
        print(c.red(f"error: schedule not found: {args.schedule}"), file=sys.stderr)
        return 2
    if not args.source_dir.is_dir():
        print(c.red(f"error: source-dir is not a directory: {args.source_dir}"), file=sys.stderr)
        return 2

    # ---- Load schedule ---------------------------------------------------
    print(c.bold(f"Reading schedule: {args.schedule}"))
    try:
        refs = load_schedule_refs(args.schedule)
    except Exception as e:
        print(c.red(f"error reading schedule: {e}"), file=sys.stderr)
        return 2
    print(f"  {len(refs)} rows with valid cust_refs")

    # ---- Match files -----------------------------------------------------
    scan_label = "recursive" if args.recursive else "top-level only"
    print(c.bold(f"Scanning {args.source_dir} ({scan_label})"))
    result = match_files(refs, args.source_dir, recursive=args.recursive)
    _print_match_summary(result, c)

    if not result.matched and not result.unmatched:
        print(c.yellow("\nno files to sort - exiting."))
        return 0

    # ---- Choose mode -----------------------------------------------------
    mode = args.mode
    if mode is None:
        choice = _prompt(
            "\nMode: [i]n-place sort  [c]opy to other location  [q]uit",
            valid=("in-place", "copy", "quit"),
        )
        if choice == "quit":
            return 0
        mode = choice

    # ---- Determine destination ------------------------------------------
    if mode == "in-place":
        dest = args.source_dir
        if args.dest_dir is not None:
            print(c.yellow("note: --dest-dir is ignored in in-place mode"))
    else:  # copy
        dest = args.dest_dir or _prompt_path("\nDestination directory")
        dest = Path(dest).expanduser().resolve()

    # ---- Build plan + resolve duplicates + check collisions -------------
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

    # ---- Confirm ---------------------------------------------------------
    op_word = "move" if mode == "in-place" else "copy"
    print()
    print(c.bold(f"Ready to {op_word} {len(plan.operations)} file(s) into {dest}"))
    if not args.yes:
        if _prompt(f"Proceed?", valid=("yes", "no"), default="no") != "yes":
            print(c.yellow("cancelled."))
            return 0

    # ---- Execute ---------------------------------------------------------
    print()
    gerund = "Moving" if op_word == "move" else "Copying"
    print(c.bold(f"{gerund} files..."))
    counts = execute_plan(
        plan,
        mode="move" if mode == "in-place" else "copy",
        on_progress=lambda d, t, s: _print_progress(d, t, s, c),
    )

    # ---- Optional cleanup of empty dirs ---------------------------------
    if args.clean_empty_dirs:
        cleanup_root = args.source_dir if mode == "in-place" else dest
        removed = clean_empty_dirs(cleanup_root)
        print(f"  removed {removed} empty subdirectories under {cleanup_root}")

    # ---- Done ------------------------------------------------------------
    print()
    print(c.green(c.bold("Done.")))
    print(f"  destination: {dest}")
    for name in ("Drawings", "Documents", "Undefined", "Unmatched"):
        n = counts.get(name, 0)
        if n:
            print(f"  {name:<12s} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
