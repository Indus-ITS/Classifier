"""CSV-driven planner for sort-by-source.

The documents table is the master list. For each row we locate its file(s) on
disk and emit ONE preferred copy into a bucket named by the row's ``doc_source``
-- so a bucket can never exceed that doc_source's row count. Matching key:

* row ``customer_ref`` is a ``\\d2-\\d2-\\d2-\\d4`` pattern  -> match files
  whose name embeds that cust_ref (feed / deliverable).
* otherwise -> match files whose name equals the row's ``document_no``
  (proposal write-ups, whose document_no is the literal filename).

Files that no row claims AND that carry a cust_ref the table doesn't list go to
``unmatched``; files with no cust_ref that no row claims are ignored as junk.

Pure logic -- only Path operations, no filesystem reads.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from classifier.io.normalize import normalize_lookup_key
from classifier.routing.dedup import parse_entry, pick_winner

UNMATCHED = "unmatched"
_CUST_REF = re.compile(r"\d{2}-\d{2}-\d{2}-\d{4}")


@dataclass(frozen=True)
class DocRow:
    customer_ref: str
    document_no: str
    doc_source: str   # lowercased
    doc_type: str      # lowercased; may be ""


@dataclass(frozen=True)
class CopyAction:
    src: Path
    bucket: str
    key: str                 # the matched key (cust_ref or filename), or cust_ref for unmatched
    matched: bool
    doc_source: str          # row doc_source ("" for unmatched leftovers)
    chosen_format: str
    related: tuple[Path, ...]


@dataclass(frozen=True)
class Plan:
    actions: tuple[CopyAction, ...]
    rows_without_file: tuple[str, ...]      # csv keys that matched no file
    skipped_no_preferred: tuple[str, ...]   # csv keys whose only files were non-candidate exts


def build_plan(rows: list[DocRow], files: list[Path]) -> Plan:
    entries = [parse_entry(Path(p)) for p in files]
    by_cref: dict[str, list] = {}
    by_name: dict[str, list] = {}
    for e in entries:
        if e.cust_ref:
            by_cref.setdefault(e.cust_ref, []).append(e)
        by_name.setdefault(e.path.name.strip().lower(), []).append(e)

    actions: list[CopyAction] = []
    rows_without_file: list[str] = []
    skipped: list[str] = []
    claimed: set[Path] = set()
    csv_crefs: set[str] = set()

    for row in rows:
        cref_raw = (row.customer_ref or "").strip()
        if _CUST_REF.search(cref_raw):
            key = normalize_lookup_key(cref_raw)
            csv_crefs.add(key)
            cands = list(by_cref.get(key, []))
        else:
            key = (row.document_no or "").strip().lower()
            cands = list(by_name.get(key, [])) if key else []

        if not cands:
            rows_without_file.append(key or cref_raw)
            continue
        for e in cands:
            claimed.add(e.path)
        g = pick_winner(cands, row.doc_type or None)
        if g.winner is None:
            skipped.append(key)
            continue
        we = next(e for e in cands if e.path == g.winner)
        actions.append(CopyAction(
            src=g.winner, bucket=(row.doc_source or UNMATCHED), key=key,
            matched=True, doc_source=row.doc_source,
            chosen_format=we.ext, related=g.related,
        ))

    # Leftovers carrying a cust_ref the table doesn't list -> unmatched.
    leftover: dict[str, list] = {}
    for e in entries:
        if e.path in claimed or not e.cust_ref or e.cust_ref in csv_crefs:
            continue
        leftover.setdefault(e.cust_ref, []).append(e)
    for cref in sorted(leftover):
        es = leftover[cref]
        g = pick_winner(es, None)
        if g.winner is None:
            continue
        we = next(e for e in es if e.path == g.winner)
        actions.append(CopyAction(
            src=g.winner, bucket=UNMATCHED, key=cref, matched=False,
            doc_source="", chosen_format=we.ext, related=g.related,
        ))

    return Plan(tuple(actions), tuple(rows_without_file), tuple(skipped))
