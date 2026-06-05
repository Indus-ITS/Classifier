"""Perform the planned copies. The only filesystem-mutating module in the
router."""
from __future__ import annotations

import shutil
from pathlib import Path

from classifier.routing.plan import Plan, CopyAction


def execute(plan: Plan, *, dry_run: bool) -> list[CopyAction]:
    """Copy each winner into its dest bucket (shutil.copy2). Creates parent
    dirs. No-op when dry_run. Returns the actions performed."""
    if dry_run:
        return []
    done: list[CopyAction] = []
    for a in plan.actions:
        a.dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(a.src, a.dest)
        done.append(a)
    return done
