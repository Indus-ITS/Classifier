"""Pretty-printers for sort-files: match summary, plan summary, progress bar."""
from __future__ import annotations

import sys
from pathlib import Path

from classifier.cli.colors import _Color
from classifier.routing.analysis import (
    plan_summary,
    plan_summary_by_class_discipline,
)


def _print_match_summary(result, c: _Color) -> None:
    matched = len(result.matched)
    unrec = len(result.unmatched_unrecognized)
    not_in = len(result.unmatched_not_in_schedule)
    no_files = len(result.refs_without_files)

    print()
    print(c.bold("Matching summary"))
    print(f"  {c.green(f'{matched:>5}')} files matched to a schedule row")
    print(f"  {c.yellow(f'{unrec:>5}')} files with no recognizable cust_ref in filename")
    print(f"  {c.yellow(f'{not_in:>5}')} files whose cust_ref is not in the schedule")
    print(f"  {c.dim(f'{no_files:>5}')} schedule rows with no file on disk")


def _print_plan_summary(plan, c: _Color) -> None:
    counts = plan_summary(plan)
    grid = plan_summary_by_class_discipline(plan)
    print()
    print(c.bold("Proposed split (class / discipline / file)"))
    colors = {
        "Drawings": c.cyan, "Documents": c.green,
        "Undefined": c.yellow, "Unmatched": c.red,
    }
    total = sum(counts.values())
    for name in ("Drawings", "Documents", "Undefined", "Unmatched"):
        n = counts.get(name, 0)
        if n == 0:
            continue
        color = colors[name]
        bar_len = int(40 * n / total) if total else 0
        print(f"  {color(name + '/'):<28s} {n:>5}  {color(c.block * bar_len)}")
        disc_counts = grid.get(name, {})
        for disc in sorted(disc_counts.keys()):
            n_d = disc_counts[disc]
            label = disc if disc != "-" else "(no discipline)"
            print(f"    {c.dim(c.branch)} {label:<22s} {n_d:>5}")


def _print_progress(done: int, total: int, src: Path, c: _Color) -> None:
    bar_w = 30
    filled = int(bar_w * done / total) if total else bar_w
    bar = c.block * filled + c.empty * (bar_w - filled)
    sys.stdout.write(
        f"\r  {c.cyan(bar)} {done:>4}/{total}  {c.dim(src.name[:50])}"
    )
    sys.stdout.flush()
    if done == total:
        sys.stdout.write("\n")
