"""Execute a route plan: copy or move files, optionally clean empty dirs."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

from classifier.routing.plan import RoutePlan, _class_folder_for

ProgressCallback = Callable[[int, int, Path], None]


def clean_empty_dirs(root: Path) -> int:
    """Remove empty directories under root, recursively (deepest first).
    Returns the count of removed directories. Never removes root itself.
    """
    if not root.is_dir():
        return 0
    removed = 0
    all_dirs = sorted(
        (p for p in root.rglob("*") if p.is_dir()),
        key=lambda p: -len(p.parts),
    )
    for d in all_dirs:
        try:
            d.rmdir()
            removed += 1
        except OSError:
            pass
    return removed


def execute_plan(
    plan: RoutePlan,
    mode: str,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[str, int]:
    """Perform the copy or move. Returns counts per top-level class folder
    (Drawings / Documents / Undefined / Unmatched).

    mode: 'copy' or 'move'.
    on_progress: optional callable(done, total, src) called after each op.
    """
    if mode not in ("copy", "move"):
        raise ValueError(f"mode must be 'copy' or 'move', got {mode!r}")

    counts: dict[str, int] = {}
    total = len(plan.operations)
    for i, (src, dst) in enumerate(plan.operations, start=1):
        cls = _class_folder_for(dst)
        if src.resolve() == dst.resolve():
            counts[cls] = counts.get(cls, 0) + 1
            if on_progress:
                on_progress(i, total, src)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if mode == "copy":
            shutil.copy2(src, dst)
        else:  # move
            shutil.move(str(src), str(dst))
        counts[cls] = counts.get(cls, 0) + 1
        if on_progress:
            on_progress(i, total, src)
    return counts
