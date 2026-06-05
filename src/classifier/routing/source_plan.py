"""Pure planner for sort-by-source: route one preferred file per logical
document into doc_source buckets, splitting matched vs unmatched by the
documents table. No I/O (Path arithmetic only)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from classifier.routing.dedup import group_files, pick_winner

UNMATCHED = "unmatched"


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
    customer_ref -> doc_type (membership decides matched)."""
    actions: list[SourceCopyAction] = []
    skipped: list[tuple[str, str]] = []
    for label, paths in sources:
        groups = group_files(list(paths))
        for group_key in sorted(groups):
            entries = groups[group_key]
            cust_ref = next((e.cust_ref for e in entries if e.cust_ref), None)
            matched = cust_ref is not None and cust_ref in doc_index
            bucket = label if matched else UNMATCHED
            doc_type = doc_index.get(cust_ref) if matched else None
            g = pick_winner(entries, doc_type)
            if g.winner is None:
                skipped.append((label, group_key))
                continue
            we = next(e for e in entries if e.path == g.winner)
            actions.append(SourceCopyAction(
                src=g.winner, bucket=bucket, customer_ref=cust_ref,
                matched=matched, chosen_format=we.ext, related=g.related,
            ))
    return SourcePlan(tuple(actions), tuple(skipped))
