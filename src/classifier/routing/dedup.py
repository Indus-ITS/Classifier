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

    When a ``cust_ref`` is present anywhere in the stem, it is the group
    key — every file sharing that cust_ref is the same logical document,
    regardless of trailing descriptive text (e.g.
    ``16-01-39-2602- SPI EXECUTION PHILOSOPHY_IFA.docx`` and
    ``16-01-39-2602-B.pdf`` both group under ``16-01-39-2602``).

    Revision parsing only fires when the tail after the cust_ref is a
    bare rev token like ``-B``, ``_1``, or ``_Rev.A``. Otherwise the
    revision is reported as ``None`` and downstream tie-breaking falls
    back to format priority.
    """
    m = CUST_REF.search(stem)
    if m:
        suffix = stem[m.end() :]
        rev = _REV_AFTER_CUST_REF.match(suffix)
        revision = rev.group(1).upper() if rev else None
        return m.group(0).lower(), revision
    rev = _REV_TAIL_FALLBACK.search(stem)
    if rev:
        return stem[: rev.start()].strip().lower(), rev.group(1).upper()
    return stem.strip().lower(), None


PREFERRED_EXTS: tuple[str, ...] = ("pdf", "doc", "docx", "xls", "xlsx")
FORMAT_PRIORITY: dict[str, int] = {
    "pdf": 0,
    "doc": 1,
    "docx": 1,
    "xls": 2,
    "xlsx": 2,
}


@dataclass(frozen=True)
class FileEntry:
    path: Path
    group_key: str
    revision: str | None
    rev_rank: tuple[int, str]
    ext: str  # lowercase, no leading dot


@dataclass(frozen=True)
class DedupResult:
    primary: Path
    related: tuple[Path, ...]


def _rev_rank(revision: str | None) -> tuple[int, str]:
    """Sort key for revisions. Larger == newer.

    Bucket -1: no revision detected.
    Bucket  0: letter revision (draft).
    Bucket  1: digit revision (issued).
    """
    if revision is None:
        return (-1, "")
    if revision.isdigit():
        return (1, revision)
    return (0, revision.upper())


def parse_entry(path: Path) -> FileEntry:
    group_key, revision = parse_stem(path.stem)
    ext = path.suffix.lstrip(".").lower()
    return FileEntry(
        path=path,
        group_key=group_key,
        revision=revision,
        rev_rank=_rev_rank(revision),
        ext=ext,
    )


def group_and_pick(files: Iterable[Path]) -> dict[str, DedupResult]:
    """Group files by ``group_key`` and pick one winner per group.

    Returns a mapping ``group_key -> DedupResult``. Groups with no
    candidate in :data:`PREFERRED_EXTS` are omitted from the result.
    """
    groups: dict[str, list[FileEntry]] = defaultdict(list)
    for f in files:
        entry = parse_entry(f)
        groups[entry.group_key].append(entry)

    out: dict[str, DedupResult] = {}
    for key, entries in groups.items():
        candidates = [e for e in entries if e.ext in PREFERRED_EXTS]
        if not candidates:
            continue
        candidates.sort(
            key=lambda e: (
                e.rev_rank,
                -FORMAT_PRIORITY[e.ext],
                str(e.path),
            ),
            reverse=True,
        )
        winner = candidates[0]
        related = tuple(
            sorted(
                (e.path for e in entries if e.path != winner.path),
                key=str,
            )
        )
        out[key] = DedupResult(primary=winner.path, related=related)
    return out
