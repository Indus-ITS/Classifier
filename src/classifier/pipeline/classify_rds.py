"""Classify and update unclassified rows in a PostgreSQL ``documents`` table.

Public API: ``classify_from_rds(conn, ...) -> stats``. See
``docs/superpowers/specs/2026-05-25-rds-pipeline-design.md`` §4.
"""
from __future__ import annotations

import logging
import time
from collections import Counter
from pathlib import Path
from typing import Callable

from classifier.io.rds import iter_unclassified, update_row
from classifier.pipeline._row import (
    fill_discipline, fill_type, normalize_doc_type,
)

log = logging.getLogger("classifier.rds")

TYPE_KEYWORDS_PATH = Path("src/classifier/config/type_keywords.py")
DISCIPLINE_KEYWORDS_PATH = Path("src/classifier/config/discipline_keywords.py")
TYPE_TO_DISCIPLINE_PATH = Path("src/classifier/config/type_to_discipline.py")
CLASSIFIED_CSV_DIR = Path("input/classified_csv")

_GENERATED_CONFIGS: tuple[tuple[Path, str], ...] = (
    (TYPE_KEYWORDS_PATH,       "learn-type-keywords"),
    (DISCIPLINE_KEYWORDS_PATH, "learn-discipline-keywords"),
    (TYPE_TO_DISCIPLINE_PATH,  "learn-type-discipline"),
)


def _stale_rule_warnings() -> list[str]:
    """Return a list of human-readable warnings for stale generated configs."""
    warnings: list[str] = []
    if not CLASSIFIED_CSV_DIR.exists():
        return warnings
    csv_mtimes = [p.stat().st_mtime for p in CLASSIFIED_CSV_DIR.rglob("*.csv")]
    if not csv_mtimes:
        return warnings
    newest_csv = max(csv_mtimes)
    for path, tool in _GENERATED_CONFIGS:
        if path.exists() and newest_csv > path.stat().st_mtime:
            warnings.append(f"{path.name} is older than training data; run {tool}")
    return warnings


def _empty_stats() -> dict:
    return {
        "rows_scanned": 0,
        "rows_updated": 0,
        "rows_skipped": 0,
        "doc_type":      Counter(),
        "type":          Counter(),
        "discipline_id": Counter(),
        "callback_error": None,
    }


def _finalize_stats(stats: dict) -> dict:
    """Convert internal Counters to plain dicts for caller convenience."""
    for k in ("doc_type", "type", "discipline_id"):
        stats[k] = dict(stats[k])
    return stats


def classify_from_rds(
    conn,
    *,
    table: str = "documents",
    pk: str = "document_id",
    commit_every: int = 500,
    fetch_size: int = 1000,
    on_done: Callable[[dict], None] | None = None,
) -> dict:
    """See spec §4. Caller owns the connection lifecycle."""
    for w in _stale_rule_warnings():
        log.warning(w)

    stats = _empty_stats()
    log.info("classify_from_rds start: table=%s pk=%s", table, pk)
    start = time.monotonic()

    write_cur = conn.cursor()
    try:
        for processed, row in enumerate(
            iter_unclassified(conn, table=table, pk=pk, fetch_size=fetch_size),
            start=1,
        ):
            pk_value, cur_doc_type, cur_type, cur_disc, title = row
            stats["rows_scanned"] += 1

            # Normalise None to "" so the pure helpers always see strings.
            cur_doc_type_s = "" if cur_doc_type is None else str(cur_doc_type)
            cur_type_s     = "" if cur_type     is None else str(cur_type)
            cur_disc_s     = "" if cur_disc     is None else str(cur_disc)
            title_s        = "" if title        is None else str(title)

            new_doc_type, dt_reason = normalize_doc_type(cur_doc_type_s, title_s)
            new_type,     t_reason  = fill_type(cur_type_s, title_s)
            # Use the effective type (whether existing or just inferred) as
            # the discipline scorer's hint -- types carry strong discipline
            # signal (e.g. ISO -> Piping, PFD -> Process).
            new_disc,     d_reason  = fill_discipline(cur_disc_s, title_s, type_hint=new_type)

            stats["doc_type"][dt_reason]      += 1
            stats["type"][t_reason]           += 1
            stats["discipline_id"][d_reason]  += 1

            writes: dict = {}

            # doc_type: write whenever the normalised value differs from
            # what's currently stored (handles both empty and alias cases).
            if new_doc_type != cur_doc_type_s.strip().lower():
                writes["doc_type"] = new_doc_type

            # type: only when existing was empty AND inference produced a value.
            if cur_type_s == "" and new_type != "":
                writes["type"] = new_type

            # discipline_id: only when existing was NULL AND inference hit.
            if cur_disc is None and new_disc != "":
                writes["discipline_id"] = int(new_disc)

            if update_row(write_cur, table=table, pk=pk, pk_value=pk_value, writes=writes):
                stats["rows_updated"] += 1
            else:
                stats["rows_skipped"] += 1

            if processed % commit_every == 0:
                conn.commit()
                elapsed = time.monotonic() - start
                rate = processed / elapsed if elapsed > 0 else 0.0
                log.info(
                    "progress: scanned=%d updated=%d elapsed=%.1fs rate=%.1f rows/s",
                    stats["rows_scanned"], stats["rows_updated"], elapsed, rate,
                )

        conn.commit()
    finally:
        write_cur.close()

    elapsed = time.monotonic() - start
    log.info(
        "done: scanned=%d updated=%d skipped=%d elapsed=%.1fs",
        stats["rows_scanned"], stats["rows_updated"], stats["rows_skipped"], elapsed,
    )

    stats = _finalize_stats(stats)

    if on_done is not None:
        try:
            on_done(stats)
        except Exception as e:  # callback isolation -- never propagate
            log.warning("on_done callback raised: %r", e)
            stats["callback_error"] = repr(e)

    return stats
