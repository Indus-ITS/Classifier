"""Console entry point: run classify_from_rds against env-var DSN.

Reads PGHOST / PGDATABASE / PGUSER / PGPASSWORD / PGPORT (optional)
from the environment, opens a connection, runs the pipeline, prints
the stats summary on completion. Real callers pass their own
connection -- this script is a convenience for ops / smoke runs.
"""
from __future__ import annotations

import logging
import os
import sys

import psycopg2

from classifier.pipeline.classify_rds import classify_from_rds


def _print_stats(stats: dict) -> None:
    print()
    print(f"scanned: {stats['rows_scanned']}")
    print(f"updated: {stats['rows_updated']}")
    print(f"skipped: {stats['rows_skipped']}")
    print(f"doc_type:      {stats['doc_type']}")
    print(f"type:          {stats['type']}")
    print(f"discipline_id: {stats['discipline_id']}")
    if stats.get("callback_error"):
        print(f"callback_error: {stats['callback_error']}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        conn = psycopg2.connect(
            host=os.environ["PGHOST"],
            dbname=os.environ["PGDATABASE"],
            user=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
            port=os.environ.get("PGPORT", "5432"),
        )
    except KeyError as e:
        sys.exit(f"missing required env var: {e.args[0]}")

    try:
        classify_from_rds(conn, on_done=_print_stats)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
