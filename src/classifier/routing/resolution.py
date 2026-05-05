"""Resolve duplicate destinations within a route plan."""
from __future__ import annotations

from pathlib import Path

from classifier.routing.plan import RoutePlan


def resolve_duplicates(
    plan: RoutePlan,
    strategy: str,
) -> tuple[RoutePlan, int, int]:
    """Resolve cases where two source files would land at the same
    destination, or a destination already exists on disk.

    strategy:
      'error'  - leave the plan untouched; find_collisions() will flag
                 these and the CLI will abort. Safe default.
      'skip'   - keep the first occurrence by source-path order, drop
                 the rest from the plan. Use when duplicates are most
                 likely identical re-sends across transmittals.
      'rename' - keep all by appending a numeric suffix to the destination
                 name (foo.pdf, foo-2.pdf, foo-3.pdf, ...). Use when
                 you want to preserve every file even at the cost of
                 cluttered names.

    Returns (resolved_plan, dropped_count, renamed_count).

    No-op operations (src == dst, in-place re-run safety) are passed
    through regardless of strategy.
    """
    if strategy not in ("error", "skip", "rename"):
        raise ValueError(f"on_duplicate must be 'error', 'skip', or 'rename', got {strategy!r}")
    if strategy == "error":
        return plan, 0, 0

    seen_dsts: set[Path] = set()
    for _, dst in plan.operations:
        if dst.exists():
            seen_dsts.add(dst)

    new_ops: list[tuple[Path, Path]] = []
    dropped = 0
    renamed = 0

    for src, dst in plan.operations:
        if src.resolve() == dst.resolve():
            new_ops.append((src, dst))
            continue

        if dst in seen_dsts:
            if strategy == "skip":
                dropped += 1
                continue
            else:  # rename
                base = dst.stem
                ext = dst.suffix
                parent = dst.parent
                i = 2
                candidate = parent / f"{base}-{i}{ext}"
                while candidate in seen_dsts or candidate.exists():
                    i += 1
                    candidate = parent / f"{base}-{i}{ext}"
                seen_dsts.add(candidate)
                new_ops.append((src, candidate))
                renamed += 1
                continue

        seen_dsts.add(dst)
        new_ops.append((src, dst))

    return RoutePlan(operations=new_ops), dropped, renamed
