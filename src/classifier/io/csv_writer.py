"""Generic CSV writer for the audit row schema (33 columns)."""
from __future__ import annotations

import csv
from pathlib import Path

from classifier.config.schema import CSV_COLUMNS


def _csv_value(v) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return ""
    return str(v)


def write_csv(rows: list, path) -> None:
    """Write classified rows to CSV (CSV_COLUMNS columns)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for r in rows:
            writer.writerow([_csv_value(r.get(col, "")) for col in CSV_COLUMNS])
