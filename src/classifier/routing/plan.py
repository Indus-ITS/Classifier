"""Build the copy plan from grouped files + the classification index. Pure
logic (Path arithmetic only)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from classifier.routing.dedup import pick_winner

BUCKET_FOR_DOCTYPE = {"drawing": "Drawings", "document": "Documents",
                      "sheet": "Sheets"}
UNMATCHED = "Unmatched"


@dataclass(frozen=True)
class CopyAction:
    src: Path
    dest: Path
    bucket: str
    doc_type: str
    cust_ref: str | None
    title: str
    revision: str | None
    chosen_format: str
    related: tuple[Path, ...]


@dataclass(frozen=True)
class Plan:
    actions: tuple[CopyAction, ...]
    rows_without_file: tuple[str, ...]
    skipped_no_preferred_format: tuple[str, ...]


def build_plan(groups, index, dest_dir: Path) -> Plan:
    """Per group: resolve its cust_ref -> doc_type from the index, pick the
    class-aware winner, and route it to dest_dir/bucket/winner.name.

    No collision handling is needed: a winner's basename is a pure function
    of its stem and the group_key is derived from that same stem, so two
    distinct groups can never yield the same basename in the same bucket.
    """
    actions: list[CopyAction] = []
    skipped: list[str] = []
    matched_refs: set[str] = set()

    for group_key in sorted(groups):
        entries = groups[group_key]
        cust_ref = next((e.cust_ref for e in entries if e.cust_ref), None)
        cls = index.get(cust_ref) if cust_ref else None
        doc_type = cls.doc_type if cls else None

        group = pick_winner(entries, doc_type)
        if group.winner is None:
            skipped.append(group_key)
            continue

        if cls is not None:
            matched_refs.add(cust_ref)
        if cls and cls.doc_type in BUCKET_FOR_DOCTYPE:
            bucket = BUCKET_FOR_DOCTYPE[cls.doc_type]
        else:
            bucket = UNMATCHED

        winner_entry = next(e for e in entries if e.path == group.winner)
        actions.append(CopyAction(
            src=group.winner, dest=dest_dir / bucket / group.winner.name,
            bucket=bucket, doc_type=(cls.doc_type if cls else ""),
            cust_ref=cust_ref, title=(cls.title if cls else ""),
            revision=winner_entry.revision, chosen_format=winner_entry.ext,
            related=group.related,
        ))

    rows_without_file = tuple(
        sorted(k for k in index.keys() if k not in matched_refs)
    )
    return Plan(tuple(actions), rows_without_file, tuple(skipped))
