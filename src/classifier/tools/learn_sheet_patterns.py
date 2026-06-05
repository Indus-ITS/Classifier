"""Phase-1 learning tool for the Sheets class.

Walks a deliverables directory, finds spreadsheets, joins each to its
title/type in classified.csv via the 16-01-xx-xxxx doc-number embedded
in the filename, opens the file to detect a real table, and writes an
evidence report. Produces NO change to classification behavior.

Usage:
    learn-sheet-patterns --dir "<TO CLIENT path>" \
        --csv output/classified.csv --out output/sheet_learning.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import re
from collections import Counter, defaultdict

from classifier.core.table_detect import file_has_table

csv.field_size_limit(10 ** 7)

DOCNUM_RE = re.compile(r"(\d{2}-\d{2}-\d{2}-\d{4})")
SPREADSHEET_EXTS = (".xlsx", ".xlsm", ".xls")

DEFAULT_DIR = (
    r"D:\Indus\DEST Pilot DATA\KR\HISTORIC Projects\SAHIL (Clean)"
    r"\5. Deliverables + Correspondence - Execution\Transmittals\TO CLIENT"
)


def load_titles(csv_path: str) -> dict[str, dict]:
    """Map customer_ref -> {title, type, discipline_id} from the CSV."""
    out: dict[str, dict] = {}
    with open(csv_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ref = (row.get("customer_ref") or "").strip()
            if ref and ref != "NULL":
                out[ref] = {
                    "title": row.get("title", ""),
                    "type": row.get("type", ""),
                    "discipline_id": row.get("discipline_id", ""),
                }
    return out


def find_spreadsheets(root: str):
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(SPREADSHEET_EXTS):
                yield os.path.join(dirpath, f)


def run(directory: str, csv_path: str, out_path: str) -> None:
    titles = load_titles(csv_path)
    rows = []
    for path in find_spreadsheets(directory):
        fname = os.path.basename(path)
        m = DOCNUM_RE.search(fname)
        docnum = m.group(1) if m else ""
        meta = titles.get(docnum, {})
        hit = file_has_table(path)
        rows.append({
            "docnum": docnum,
            "file": fname,
            "title": meta.get("title", ""),
            "type": meta.get("type", ""),
            "discipline_id": meta.get("discipline_id", ""),
            "has_table": "1" if hit else "0",
            "table_sheet": hit[0] if hit else "",
            "n_data_rows": hit[1].n_data_rows if hit else 0,
        })

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    _print_report(rows)


def _print_report(rows: list[dict]) -> None:
    total = len(rows)
    joined = [r for r in rows if r["type"]]
    tables = [r for r in rows if r["has_table"] == "1"]
    print(f"\nspreadsheets scanned : {total}")
    print(f"joined to a CSV title: {len(joined)}")
    print(f"detected as tables   : {len(tables)}")

    by_type_total: Counter = Counter(r["type"] for r in joined)
    by_type_table: Counter = Counter(r["type"] for r in joined if r["has_table"] == "1")
    print("\nper-type table fraction (joined files only):")
    print(f"  {'type':6} {'tables':>7} {'total':>7} {'frac':>6}")
    for t, n in by_type_total.most_common():
        tab = by_type_table.get(t, 0)
        print(f"  {t or '(blank)':6} {tab:7d} {n:7d} {tab / n:6.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Learn which titles are table-sheets.")
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--csv", default="output/classified.csv")
    ap.add_argument("--out", default="output/sheet_learning.csv")
    args = ap.parse_args()
    run(args.dir, args.csv, args.out)


if __name__ == "__main__":
    main()
