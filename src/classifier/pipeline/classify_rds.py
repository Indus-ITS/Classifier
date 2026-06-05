"""Classify and update unclassified rows in a PostgreSQL ``documents`` table.

Public API: ``classify_from_rds(conn, ...) -> stats``. See
``docs/superpowers/specs/2026-05-25-rds-pipeline-design.md`` §4.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

from classifier.io.rds import RdsReader, RdsWriter
from classifier.pipeline.run import run
from classifier.pipeline.staleness import stale_configs

log = logging.getLogger("classifier.rds")

TYPE_KEYWORDS_PATH = Path("src/classifier/config/type_keywords.py")
DISCIPLINE_KEYWORDS_PATH = Path("src/classifier/config/discipline_keywords.py")
TYPE_TO_DISCIPLINE_PATH = Path("src/classifier/config/type_to_discipline.py")
CLASSIFIED_CSV_DIR = Path("input/classified_csv")

_GENERATED_CONFIGS = (
    (TYPE_KEYWORDS_PATH,       "learn-type-keywords"),
    (DISCIPLINE_KEYWORDS_PATH, "learn-discipline-keywords"),
    (TYPE_TO_DISCIPLINE_PATH,  "learn-type-discipline"),
)


def _stats_to_dict(stats) -> dict:
    return {
        "rows_scanned": stats.rows_scanned,
        "rows_updated": stats.rows_updated,
        "rows_skipped": stats.rows_skipped,
        "doc_type": dict(stats.reasons["doc_type"]),
        "type": dict(stats.reasons["type"]),
        "discipline_id": dict(stats.reasons["discipline_id"]),
        "callback_error": stats.callback_error,
    }


def classify_from_rds(
    conn,
    *,
    table: str = "documents",
    pk: str = "document_id",
    commit_every: int = 500,
    fetch_size: int = 1000,
    on_done: Callable[[dict], None] | None = None,
) -> dict:
    for path, tool in stale_configs(list(_GENERATED_CONFIGS), CLASSIFIED_CSV_DIR):
        log.warning("%s is older than training data; run %s", path.name, tool)

    log.info("classify_from_rds start: table=%s pk=%s", table, pk)
    start = time.monotonic()

    reader = RdsReader(conn, table=table, pk=pk, fetch_size=fetch_size)
    writer = RdsWriter(conn, table=table, pk=pk, commit_every=commit_every)

    def _progress(stats) -> None:
        if stats.rows_scanned % commit_every == 0:
            elapsed = time.monotonic() - start
            rate = stats.rows_scanned / elapsed if elapsed > 0 else 0.0
            log.info("progress: scanned=%d updated=%d elapsed=%.1fs rate=%.1f rows/s",
                     stats.rows_scanned, stats.rows_updated, elapsed, rate)

    stats = run(reader, writer, on_progress=_progress)
    conn.commit()   # final commit on success only (matches old behavior: skipped on error)

    elapsed = time.monotonic() - start
    log.info("done: scanned=%d updated=%d skipped=%d elapsed=%.1fs",
             stats.rows_scanned, stats.rows_updated, stats.rows_skipped, elapsed)

    result = _stats_to_dict(stats)
    if on_done is not None:
        try:
            on_done(result)
        except Exception as e:  # callback isolation -- never propagate
            log.warning("on_done callback raised: %r", e)
            result["callback_error"] = repr(e)
    return result
