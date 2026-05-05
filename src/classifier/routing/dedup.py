"""Group source files by logical document and pick a single winner per group.

A logical document = files that share a stem after revision suffix is
stripped. Within a group, the winner is the latest revision in the
preferred format (pdf > doc/docx > xls/xlsx). Everything else in the
group is captured as ``related[]`` for audit.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CUST_REF = re.compile(r"\d{2}-\d{2}-\d{2}-\d{4}")
_REV_AFTER_CUST_REF = re.compile(
    r"^[\s_-]+(?:Rev\.?)?([A-Z]|\d)(?:[\s_.-].*)?$",
    flags=re.IGNORECASE,
)
_REV_TAIL_FALLBACK = re.compile(
    r"[\s_-]+(?:Rev\.?)?([A-Z]|\d)(?:[\s_.-].*)?$",
    flags=re.IGNORECASE,
)


def parse_stem(stem: str) -> tuple[str, str | None]:
    """Return ``(group_key, revision)`` for a filename stem.

    Anchors on the cust_ref so the trailing 4-digit segment of a bare
    cust_ref is never misread as a revision. Falls back to a whole-stem
    strip when no cust_ref is present.
    """
    m = CUST_REF.search(stem)
    if m:
        prefix, suffix = stem[: m.end()], stem[m.end() :]
        rev = _REV_AFTER_CUST_REF.match(suffix)
        if rev:
            return prefix.strip().lower(), rev.group(1).upper()
        return stem.strip().lower(), None
    rev = _REV_TAIL_FALLBACK.search(stem)
    if rev:
        return stem[: rev.start()].strip().lower(), rev.group(1).upper()
    return stem.strip().lower(), None
