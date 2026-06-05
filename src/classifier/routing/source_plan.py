"""CSV-driven planner for sort-by-source.

The documents table is the master list. For each row we locate its file(s) on
disk and emit ONE preferred-format copy into ``<doc_source>/<class>`` -- the
class (document / drawing / sheet) is derived from the row's title via the
classifier (so a bucket can never exceed that doc_source's row count, and the
familiar 3-class split appears inside each bucket). Matching key:

* row ``customer_ref`` is a ``\\d2-\\d2-\\d2-\\d4`` pattern  -> match files
  whose name embeds that cust_ref (feed / deliverable).
* otherwise -> match files whose name equals the row's ``document_no``
  (proposal write-ups, whose document_no is the literal filename).

Files that no row claims AND that carry a cust_ref the table doesn't list go to
``unmatched`` (flat, no class -- there's no title to classify); files with no
cust_ref that no row claims are ignored as junk.

Winner: preferred format first (pdf for document/drawing, xlsx for sheet),
then latest revision within that format (see ``pick_winner(format_first=True)``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from classifier.core.classify import classify_record
from classifier.core.record import Record
from classifier.io.normalize import normalize_lookup_key
from classifier.routing.dedup import parse_entry, pick_winner

UNMATCHED = "unmatched"
_CUST_REF = re.compile(r"\d{2}-\d{2}-\d{2}-\d{4}")


@dataclass(frozen=True)
class DocRow:
    customer_ref: str
    document_no: str
    doc_source: str   # lowercased
    title: str


@dataclass(frozen=True)
class CopyAction:
    src: Path
    bucket: str               # doc_source, or "unmatched"
    doc_class: str            # document/drawing/sheet; "" for unmatched (no title)
    key: str
    matched: bool
    chosen_format: str
    related: tuple[Path, ...]


@dataclass(frozen=True)
class Plan:
    actions: tuple[CopyAction, ...]
    rows_without_file: tuple[str, ...]
    skipped_no_preferred: tuple[str, ...]


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
        doc_class = classify_record(Record(title=row.title or "")).doc_type.value
        g = pick_winner(cands, doc_class, format_first=True)
        if g.winner is None:
            skipped.append(key)
            continue
        we = next(e for e in cands if e.path == g.winner)
        actions.append(CopyAction(
            src=g.winner, bucket=(row.doc_source or UNMATCHED), doc_class=doc_class,
            key=key, matched=True, chosen_format=we.ext, related=g.related,
        ))

    # Leftovers carrying a cust_ref the table doesn't list -> unmatched (flat).
    leftover: dict[str, list] = {}
    for e in entries:
        if e.path in claimed or not e.cust_ref or e.cust_ref in csv_crefs:
            continue
        leftover.setdefault(e.cust_ref, []).append(e)
    for cref in sorted(leftover):
        es = leftover[cref]
        g = pick_winner(es, None, format_first=True)
        if g.winner is None:
            continue
        we = next(e for e in es if e.path == g.winner)
        actions.append(CopyAction(
            src=g.winner, bucket=UNMATCHED, doc_class="", key=cref,
            matched=False, chosen_format=we.ext, related=g.related,
        ))

    return Plan(tuple(actions), tuple(rows_without_file), tuple(skipped))
