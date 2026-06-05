"""Pure planner for sort-by-source: route one preferred file per logical
document into doc_source buckets, splitting matched vs unmatched by the
documents table. No I/O (Path arithmetic only)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from classifier.routing.dedup import parse_entry, pick_winner

UNMATCHED = "unmatched"
_NOREF = "\x00noref\x00"


@dataclass(frozen=True)
class SourceCopyAction:
    src: Path
    bucket: str
    customer_ref: str | None
    matched: bool
    chosen_format: str
    related: tuple[Path, ...]


@dataclass(frozen=True)
class SourcePlan:
    actions: tuple[SourceCopyAction, ...]
    skipped_no_preferred: tuple[tuple[str, str], ...]


def build_source_plan(sources, doc_index: dict[str, str]) -> SourcePlan:
    """sources: iterable of (label, [Path]). doc_index: normalized
    customer_ref -> doc_type.

    Bucketing:
      * cust_ref present AND in doc_index  -> the source label (matched).
      * cust_ref present but NOT in doc_index -> "unmatched" (a stranger).
      * no cust_ref at all -> the source label (kept in its source bucket;
        we simply can't table-verify it).

    Grouping is by ``customer_ref`` when present, so exactly ONE preferred file
    is emitted per documents-table row (all files sharing a cust_ref — main
    doc, Comment Response Sheet, alternate formats — collapse to one winner).
    Files with no cust_ref are grouped by their rev-stripped stem instead.
    """
    actions: list[SourceCopyAction] = []
    skipped: list[tuple[str, str]] = []
    for label, paths in sources:
        groups: dict[str, list] = {}
        for p in paths:
            e = parse_entry(Path(p))
            key = e.cust_ref if e.cust_ref else f"{_NOREF}{e.group_key}"
            groups.setdefault(key, []).append(e)
        for key in sorted(groups):
            entries = groups[key]
            cust_ref = entries[0].cust_ref  # shared across the group; None for no-ref
            if cust_ref is None:
                bucket, matched, doc_type = label, False, None
            elif cust_ref in doc_index:
                bucket, matched, doc_type = label, True, doc_index[cust_ref]
            else:
                bucket, matched, doc_type = UNMATCHED, False, None
            g = pick_winner(entries, doc_type)
            if g.winner is None:
                skipped.append((label, key))
                continue
            we = next(e for e in entries if e.path == g.winner)
            actions.append(SourceCopyAction(
                src=g.winner, bucket=bucket, customer_ref=cust_ref,
                matched=matched, chosen_format=we.ext, related=g.related,
            ))
    return SourcePlan(tuple(actions), tuple(skipped))
