"""Top-level folder names produced by sort-files.

Shared by matching (to skip these on recursive re-runs), plan (build),
analysis (summaries), and execute (class lookup).
"""
from __future__ import annotations

CLASS_FOLDERS: tuple[str, ...] = ("Drawings", "Documents", "Undefined")
UNMATCHED_FOLDER: str = "Unmatched"
_CLASS_DIR_NAMES = frozenset((*CLASS_FOLDERS, UNMATCHED_FOLDER))
