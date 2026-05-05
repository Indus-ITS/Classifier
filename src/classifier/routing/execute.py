"""Execute a route plan: copy files into class folders."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

from classifier.routing.plan import RoutePlan, _class_folder_for

ProgressCallback = Callable[[int, int, Path], None]


def execute_plan(
    plan: RoutePlan,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[str, int]:
    """Copy each planned source -> dest. Returns counts per class folder."""
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
        shutil.copy2(src, dst)
        counts[cls] = counts.get(cls, 0) + 1
        if on_progress:
            on_progress(i, total, src)
    return counts
