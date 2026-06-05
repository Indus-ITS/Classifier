"""Shared detection of generated configs older than the labelled training CSVs.

Returns the stale (path, learner-command) pairs; callers format/emit in their
own style (the CSV CLI prints, the RDS pipeline logs).
"""
from __future__ import annotations

from pathlib import Path


def stale_configs(configs: list[tuple[Path, str]], csv_dir: Path
                  ) -> list[tuple[Path, str]]:
    if not csv_dir.exists():
        return []
    mtimes = [p.stat().st_mtime for p in csv_dir.rglob("*.csv")]
    if not mtimes:
        return []
    newest = max(mtimes)
    return [(p, tool) for p, tool in configs
            if p.exists() and newest > p.stat().st_mtime]
