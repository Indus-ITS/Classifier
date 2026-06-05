"""Logical-document grouping and class-aware winner selection. Pure logic;
only Path operations, no filesystem reads.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from classifier.io.normalize import normalize_lookup_key
from classifier.routing.cust_ref import extract_cust_ref, parse_group_and_revision

CANDIDATE_EXTS = ("pdf", "doc", "docx", "xls", "xlsx")

FORMAT_PRIORITY_DOC = {"pdf": 0, "doc": 1, "docx": 1, "xls": 2, "xlsx": 2}
FORMAT_PRIORITY_SHEET = {"xlsx": 0, "xls": 1, "pdf": 2, "doc": 3, "docx": 3}


def format_priority(ext: str, doc_type: str | None) -> int:
    """Lower = preferred. 'sheet' prefers spreadsheets; everything else
    (incl. unknown/None) prefers pdf. Non-candidate exts return a large
    sentinel so they never win."""
    table = FORMAT_PRIORITY_SHEET if doc_type == "sheet" else FORMAT_PRIORITY_DOC
    return table.get(ext, 99)


def _rev_rank(revision: str | None) -> tuple[int, object]:
    if revision is None:
        return (-1, "")
    if revision.isdigit():
        return (1, int(revision))
    return (0, revision)


@dataclass(frozen=True)
class FileEntry:
    path: Path
    group_key: str
    cust_ref: str | None      # normalized; None when no cust_ref in name
    revision: str | None
    rev_rank: tuple[int, object]
    ext: str                  # lowercase, no leading dot


@dataclass(frozen=True)
class Group:
    group_key: str
    winner: Path | None
    related: tuple[Path, ...]


def parse_entry(path: Path) -> FileEntry:
    stem = path.stem
    group_key, revision = parse_group_and_revision(stem)
    raw_ref = extract_cust_ref(stem)
    cust_ref = normalize_lookup_key(raw_ref) if raw_ref else None
    ext = path.suffix.lower().lstrip(".")
    return FileEntry(
        path=path, group_key=group_key, cust_ref=cust_ref,
        revision=revision, rev_rank=_rev_rank(revision), ext=ext,
    )


def group_files(paths: Iterable[Path]) -> dict[str, list[FileEntry]]:
    groups: dict[str, list[FileEntry]] = {}
    for p in paths:
        e = parse_entry(p)
        groups.setdefault(e.group_key, []).append(e)
    return groups


def pick_winner(entries: list[FileEntry], doc_type: str | None,
                *, format_first: bool = False) -> Group:
    """Pick one winner among candidate-ext files; non-winners become `related`.

    Default (``format_first=False``): revision-first — max rev_rank, then the
    class-aware preferred format, then lexical name. (Used by the doc_type
    ``sort-files`` router.)

    ``format_first=True``: preferred-format-first — take the class's most
    preferred format that EXISTS (e.g. pdf for a document; xlsx for a sheet),
    then the latest revision *within that format*, then lexical name. So a pdf
    is chosen whenever any pdf is present; revision only decides among files of
    that same format, and only falls back to other formats when the preferred
    one is missing.
    """
    group_key = entries[0].group_key if entries else ""
    candidates = [e for e in entries if e.ext in CANDIDATE_EXTS]
    if not candidates:
        return Group(group_key, None, tuple(e.path for e in entries))
    if format_first:
        best_fp = min(format_priority(e.ext, doc_type) for e in candidates)
        tier = [e for e in candidates if format_priority(e.ext, doc_type) == best_fp]
        best_rank = max(e.rev_rank for e in tier)
        top = [e for e in tier if e.rev_rank == best_rank]
    else:
        best_rank = max(e.rev_rank for e in candidates)
        tier = [e for e in candidates if e.rev_rank == best_rank]
        best_fp = min(format_priority(e.ext, doc_type) for e in tier)
        top = [e for e in tier if format_priority(e.ext, doc_type) == best_fp]
    top.sort(key=lambda e: e.path.name)
    winner = top[0]
    related = tuple(e.path for e in entries if e.path != winner.path)
    return Group(group_key, winner.path, related)
