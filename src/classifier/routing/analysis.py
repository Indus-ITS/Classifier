"""Analysis over a route plan: per-class summaries and collision detection."""
from __future__ import annotations

from pathlib import Path

from classifier.routing.folders import CLASS_FOLDERS, UNMATCHED_FOLDER
from classifier.routing.plan import RoutePlan


def plan_summary(plan: RoutePlan) -> dict[str, int]:
    """Count files per top-level class folder (Drawings / Documents /
    Undefined / Unmatched).
    """
    counts: dict[str, int] = {}
    for _, dst in plan.operations:
        parts = dst.parts
        class_name = next(
            (p for p in parts if p in CLASS_FOLDERS or p == UNMATCHED_FOLDER),
            dst.parent.name,
        )
        counts[class_name] = counts.get(class_name, 0) + 1
    return counts


def plan_summary_by_class_discipline(plan: RoutePlan) -> dict[str, dict[str, int]]:
    """Returns ``{class: {discipline: count}}`` for the matched-file ops.
    Unmatched files (no discipline level in path) are reported under
    ``Unmatched -> {'-': count}``.
    """
    out: dict[str, dict[str, int]] = {}
    for _, dst in plan.operations:
        parts = dst.parts
        class_idx = next(
            (i for i, p in enumerate(parts)
             if p in CLASS_FOLDERS or p == UNMATCHED_FOLDER),
            None,
        )
        if class_idx is None:
            continue
        cls = parts[class_idx]
        if cls == UNMATCHED_FOLDER:
            disc = "-"
        else:
            disc = parts[class_idx + 1] if class_idx + 1 < len(parts) - 1 else "_UNKNOWN"
        out.setdefault(cls, {})
        out[cls][disc] = out[cls].get(disc, 0) + 1
    return out


def find_collisions(plan: RoutePlan) -> list[Path]:
    """Return destination paths that already exist (would be overwritten).
    Detects same-source same-destination (in-place re-runs) and same-name
    collisions from different sources.
    """
    collisions: list[Path] = []
    seen_dsts: set[Path] = set()
    for src, dst in plan.operations:
        if src.resolve() == dst.resolve():
            continue
        if dst.exists() or dst in seen_dsts:
            collisions.append(dst)
        seen_dsts.add(dst)
    return collisions
